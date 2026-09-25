"""Синхронизация календарей площадок (импорт iCal) и фоновый планировщик.

Как работает импорт одного календаря:
  1. Скачиваем .ics по ссылке площадки (Авито, Яндекс Путешествия и т.д.).
  2. Каждое событие = занятые даты на площадке. Создаём/обновляем бронь с source=<канал>.
  3. Событие исчезло из календаря → бронь отменена на площадке → отменяем у себя.
  4. Если даты уже заняты другой бронью:
       — площадка уже видела нашу бронь (забирала наш календарь после её создания) →
         это «эхо» нашей же брони, пропускаем;
       — иначе это настоящее двойное бронирование → записываем конфликт, владелец видит предупреждение.
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx
import psycopg

from . import config, ical
from .db import all_, one, run, tx

log = logging.getLogger("fligel.sync")

MAX_FEED_BYTES = 5 * 1024 * 1024
CHANNEL_LABELS = {"avito": "Авито", "yandex": "Яндекс Путешествия", "sutochno": "Суточно.ру",
                  "ostrovok": "Островок", "other": "Другая площадка"}


@dataclass
class SyncResult:
    status: str = "ok"
    added: int = 0
    updated: int = 0
    removed: int = 0
    conflicts: int = 0
    echoes: int = 0
    message: str = ""
    conflict_details: list = field(default_factory=list)


def fetch(url: str) -> str:
    headers = {"User-Agent": "Fligel-Calendar-Sync/1.0", "Accept": "text/calendar, */*"}
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Площадка ответила кодом {resp.status_code}")
            chunks, size = [], 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > MAX_FEED_BYTES:
                    raise RuntimeError("Календарь слишком большой (больше 5 МБ)")
                chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


def _covered(ev: ical.Event, bookings: list[dict]) -> bool:
    nights: set[date] = set()
    for b in bookings:
        d = b["check_in"]
        while d < b["check_out"]:
            nights.add(d)
            d += timedelta(days=1)
    d = ev.start
    while d < ev.end:
        if d not in nights:
            return False
        d += timedelta(days=1)
    return True


def _last_export(conn, target_id, channel: str):
    row = one(conn, "SELECT last_fetched_at FROM ical_exports WHERE target_id = %s AND channel = %s",
              (target_id, channel))
    return row["last_fetched_at"] if row else None


def _feed_rooms(conn, feed: dict) -> list[dict]:
    if feed["room_id"]:
        return [{"id": feed["room_id"]}]
    return all_(conn, "SELECT id FROM rooms WHERE room_type_id = %s ORDER BY sort_order, name",
                (feed["room_type_id"],))


def _place(conn, feed: dict, rooms: list[dict], ev: ical.Event, uid: str, existing: dict | None) -> bool:
    """Ставит бронь площадки в номер. Для категории — в любой свободный номер этой категории.
    Возвращает False, если свободного номера нет."""
    candidates = [r["id"] for r in rooms]
    if existing:  # сначала пробуем оставить гостя в том же номере
        candidates.sort(key=lambda rid: rid != existing["room_id"])
    for room_id in candidates:
        try:
            with conn.transaction():
                if existing:
                    run(conn,
                        "UPDATE bookings SET room_id = %s, check_in = %s, check_out = %s, status = 'confirmed',"
                        " notes = %s, updated_at = now() WHERE id = %s",
                        (room_id, ev.start, ev.end, ev.summary[:500], existing["id"]))
                else:
                    run(conn,
                        "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status,"
                        " source, notes, feed_id, external_uid)"
                        " VALUES (%s, %s, %s, %s, %s, 'confirmed', %s, %s, %s, %s)",
                        (feed["account_id"], feed["property_id"], room_id, ev.start, ev.end,
                         feed["channel"], ev.summary[:500], feed["id"], uid))
            return True
        except psycopg.errors.ExclusionViolation:
            continue
    return False


def apply_events(conn, feed: dict, events: list[ical.Event], today: date | None = None) -> SyncResult:
    """Применяет события календаря площадки к броням. Вызывается внутри транзакции.

    Защита от «эха»: площадка может вернуть в своём календаре наши же брони, которые она
    получила от нас. Такое событие мы узнаём, если площадка уже забирала наш календарь после
    того, как эта бронь появилась, и событие совпадает с нашими бронями по датам.
    """
    today = today or date.today()
    res = SyncResult()
    rooms = _feed_rooms(conn, feed)
    room_ids = [r["id"] for r in rooms]
    target = feed["room_id"] or feed["room_type_id"]
    exported_at = _last_export(conn, target, feed["channel"])
    existing = {
        b["external_uid"]: b
        for b in all_(conn, "SELECT * FROM bookings WHERE feed_id = %s", (feed["id"],))
    }
    # Наши брони (не с этой площадки), которые площадка уже видела — кандидаты на «эхо»
    ours = all_(
        conn,
        "SELECT b.id, b.room_id, b.check_in, b.check_out, b.updated_at FROM bookings b"
        " LEFT JOIN ical_feeds f ON f.id = b.feed_id"
        " WHERE b.room_id = ANY(%s::uuid[]) AND b.status <> 'cancelled' AND b.check_out >= %s"
        " AND (f.channel IS NULL OR f.channel <> %s)",
        (room_ids, today, feed["channel"]),
    ) if exported_at else []
    visible = [b for b in ours if b["updated_at"] <= exported_at]
    echo_used: set = set()
    seen: set[str] = set()
    uid_counts: dict[str, int] = {}  # одинаковые UID в одном календаре встречаются
    for ev in events:
        if ev.cancelled or ev.end < today:
            continue
        if ev.uid.endswith("@fligel"):
            continue  # наше собственное событие вернулось как есть
        n = uid_counts.get(ev.uid, 0)
        uid_counts[ev.uid] = n + 1
        uid = ev.uid if n == 0 else f"{ev.uid}#{n}"
        b = existing.get(uid)
        if b and b["status"] != "cancelled" and b["check_in"] == ev.start and b["check_out"] == ev.end:
            seen.add(uid)
            continue  # ничего не изменилось
        if not b:
            # Эхо для категории: событие точь-в-точь совпадает с нашей бронью, которую площадка видела
            twin = next((o for o in visible if o["id"] not in echo_used
                         and o["check_in"] == ev.start and o["check_out"] == ev.end), None)
            if twin and feed["room_type_id"]:
                echo_used.add(twin["id"])
                res.echoes += 1
                continue
        seen.add(uid)
        if _place(conn, feed, rooms, ev, uid, b):
            if b:
                res.updated += 1
            else:
                res.added += 1
            continue
        # Места нет. Эхо для номера: событие целиком покрыто нашими бронями, которые площадка видела
        if feed["room_id"]:
            overlap = [o for o in ours if o["check_in"] < ev.end and o["check_out"] > ev.start]
            if overlap and all(o["updated_at"] <= exported_at for o in overlap) and _covered(ev, overlap):
                res.echoes += 1
                seen.discard(uid)
                continue
        inserted = one(
            conn,
            "INSERT INTO sync_conflicts (account_id, feed_id, room_id, room_type_id, external_uid, check_in,"
            " check_out, summary) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (feed_id, external_uid, check_in, check_out) DO NOTHING RETURNING id",
            (feed["account_id"], feed["id"], feed["room_id"], feed["room_type_id"], uid, ev.start, ev.end,
             ev.summary[:500]),
        )
        res.conflicts += 1
        if inserted:
            res.conflict_details.append({"check_in": ev.start, "check_out": ev.end})
    # Исчезнувшие из календаря будущие брони — отменены на площадке
    for uid, b in existing.items():
        if uid not in seen and b["status"] != "cancelled" and b["check_out"] >= today:
            run(conn, "UPDATE bookings SET status = 'cancelled', updated_at = now() WHERE id = %s", (b["id"],))
            res.removed += 1
    if res.conflicts:
        res.message = f"Даты заняты другой бронью: {res.conflicts}. Проверьте конфликты."
    if res.echoes:
        log.info("Календарь %s: пропущено событий-эхо: %s", feed["id"], res.echoes)
    return res


def _load_feed(conn, feed_id) -> dict | None:
    return one(
        conn,
        "SELECT f.*, coalesce(r.property_id, rt.property_id) AS property_id, p.timezone FROM ical_feeds f"
        " LEFT JOIN rooms r ON r.id = f.room_id LEFT JOIN room_types rt ON rt.id = f.room_type_id"
        " JOIN properties p ON p.id = coalesce(r.property_id, rt.property_id) WHERE f.id = %s",
        (feed_id,),
    )


def sync_feed(feed_id, fetcher=None) -> SyncResult:
    with tx() as conn:
        feed = _load_feed(conn, feed_id)
    if not feed:
        return SyncResult(status="error", message="Календарь не найден")
    try:
        text = (fetcher or fetch)(feed["url"])
        events = ical.parse(text, feed["timezone"])
    except Exception as e:  # сеть, формат, код ответа
        res = SyncResult(status="error", message=str(e)[:500] or type(e).__name__)
        with tx() as conn:
            run(conn, "UPDATE ical_feeds SET last_status = 'error', last_error = %s, last_synced_at = now()"
                      " WHERE id = %s", (res.message, feed_id))
            run(conn, "INSERT INTO sync_log (account_id, feed_id, status, message) VALUES (%s, %s, 'error', %s)",
                (feed["account_id"], feed_id, res.message))
        log.warning("Синхронизация %s (%s) не удалась: %s", feed_id, feed["channel"], res.message)
        return res
    with tx() as conn:
        # Блокируем календарь, чтобы два процесса не применяли его одновременно
        if not one(conn, "SELECT id FROM ical_feeds WHERE id = %s FOR UPDATE", (feed_id,)):
            return SyncResult(status="error", message="Календарь удалён")
        res = apply_events(conn, feed, events)
        run(conn, "UPDATE ical_feeds SET last_status = 'ok', last_error = %s, last_synced_at = now()"
                  " WHERE id = %s", (res.message or None, feed_id))
        log_msg = res.message + (f" Совпало с нашими бронями (эхо): {res.echoes}." if res.echoes else "")
        run(conn, "INSERT INTO sync_log (account_id, feed_id, status, added, updated, removed, conflicts, message)"
                  " VALUES (%s, %s, 'ok', %s, %s, %s, %s, %s)",
            (feed["account_id"], feed_id, res.added, res.updated, res.removed, res.conflicts, log_msg.strip()))
    return res


def claim_due_feeds(limit: int = 20) -> list:
    """Забираем календари, которым пора обновиться. SKIP LOCKED — безопасно при нескольких серверах."""
    with tx() as conn:
        rows = all_(
            conn,
            "SELECT f.id FROM ical_feeds f JOIN accounts a ON a.id = f.account_id"
            " WHERE f.enabled AND a.status = 'active' AND f.next_run_at <= now()"
            " ORDER BY f.next_run_at LIMIT %s FOR UPDATE OF f SKIP LOCKED",
            (limit,),
        )
        ids = [r["id"] for r in rows]
        if ids:
            run(conn, "UPDATE ical_feeds SET next_run_at = now() + make_interval(mins => %s)"
                      " WHERE id = ANY(%s::uuid[])", (config.SYNC_INTERVAL_MINUTES, ids))
    return ids


def expire_holds() -> int:
    """Неоплаченные прямые брони с истёкшим сроком удержания освобождают номер."""
    with tx() as conn:
        return run(conn, "UPDATE bookings SET status = 'cancelled', updated_at = now(),"
                         " notes = notes || ' [снято: не оплачено вовремя]'"
                         " WHERE status = 'pending' AND hold_expires_at IS NOT NULL AND hold_expires_at < now()")


def run_once() -> int:
    expire_holds()
    ids = claim_due_feeds()
    for fid in ids:
        try:
            sync_feed(fid)
        except Exception:
            log.exception("Ошибка синхронизации календаря %s", fid)
    return len(ids)


class Scheduler:
    """Фоновый поток: раз в 30 секунд проверяет, каким календарям пора обновиться."""

    def __init__(self, tick_seconds: int = 30):
        self.tick = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="ical-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        log.info("Синхронизация календарей запущена, интервал %s мин", config.SYNC_INTERVAL_MINUTES)
        while not self._stop.is_set():
            try:
                run_once()
            except Exception:
                log.exception("Сбой планировщика синхронизации")
            self._stop.wait(self.tick)


def _closed_runs(conn, room_type_id, today: date) -> list[tuple[date, date]]:
    """Даты с закрытыми продажами категории, склеенные в периоды [начало, конец)."""
    rows = all_(conn, "SELECT date FROM rates WHERE room_type_id = %s AND closed AND date >= %s ORDER BY date",
                (room_type_id, today))
    runs: list[tuple[date, date]] = []
    for r in rows:
        d = r["date"]
        if runs and runs[-1][1] == d:
            runs[-1] = (runs[-1][0], d + timedelta(days=1))
        else:
            runs.append((d, d + timedelta(days=1)))
    return runs


def _active_bookings(conn, room_ids: list, channel: str | None, today: date) -> list[dict]:
    """Активные брони номеров. channel — исключить брони, пришедшие с этой площадки."""
    return all_(
        conn,
        "SELECT b.id, b.room_id, b.check_in, b.check_out, b.status FROM bookings b"
        " LEFT JOIN ical_feeds f ON f.id = b.feed_id"
        " WHERE b.room_id = ANY(%s::uuid[]) AND b.status <> 'cancelled' AND b.check_out >= %s"
        " AND (%s::text IS NULL OR f.channel IS NULL OR f.channel <> %s) ORDER BY b.check_in",
        (room_ids, today - timedelta(days=1), channel, channel),
    )


def export_events(conn, room: dict, channel: str) -> list[ical.Event]:
    """Календарь номера для площадки: все активные брони номера, кроме пришедших с этой же площадки."""
    today = date.today()
    events = [ical.Event(uid=f"{r['id']}@fligel", start=r["check_in"], end=r["check_out"],
                         summary="Закрыто" if r["status"] == "blocked" else "Занято")
              for r in _active_bookings(conn, [room["id"]], channel, today)]
    for start, end in _closed_runs(conn, room["room_type_id"], today):
        events.append(ical.Event(uid=f"closed-{room['id']}-{start.isoformat()}@fligel", start=start, end=end,
                                 summary="Закрыто"))
    return events


def export_type_events(conn, room_type: dict, channel: str, mode: str) -> list[ical.Event]:
    """Календарь категории для площадки.
    per_booking — каждая бронь отдельным событием (кроме пришедших с этой площадки);
    sold_out — одно событие на каждый период, когда в категории не осталось свободных номеров."""
    today = date.today()
    room_ids = [r["id"] for r in all_(conn, "SELECT id FROM rooms WHERE room_type_id = %s", (room_type["id"],))]
    events: list[ical.Event] = []
    if mode == "per_booking":
        events = [ical.Event(uid=f"{r['id']}@fligel", start=r["check_in"], end=r["check_out"],
                             summary="Закрыто" if r["status"] == "blocked" else "Занято")
                  for r in _active_bookings(conn, room_ids, channel, today)]
    elif room_ids:
        # считаем все брони, включая пришедшие с этой площадки: иначе она продаст лишнее
        busy: dict[date, int] = {}
        for b in _active_bookings(conn, room_ids, None, today):
            d = max(b["check_in"], today)
            while d < b["check_out"]:
                busy[d] = busy.get(d, 0) + 1
                d += timedelta(days=1)
        full = sorted(d for d, n in busy.items() if n >= len(room_ids))
        run_start = prev = None
        for d in full + [None]:
            if d is not None and prev is not None and d == prev + timedelta(days=1):
                prev = d
                continue
            if run_start is not None:
                events.append(ical.Event(uid=f"soldout-{room_type['id']}-{run_start.isoformat()}@fligel",
                                         start=run_start, end=prev + timedelta(days=1), summary="Нет мест"))
            run_start = prev = d
    for start, end in _closed_runs(conn, room_type["id"], today):
        events.append(ical.Event(uid=f"closed-{room_type['id']}-{start.isoformat()}@fligel", start=start, end=end,
                                 summary="Закрыто"))
    return events
