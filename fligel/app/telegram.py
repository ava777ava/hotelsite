"""Уведомления в Telegram: привязка сотрудника к чату бота, очередь отправки с повторами,
утренний дайджест заездов/выездов.

Полностью выключено, пока не задан TELEGRAM_BOT_TOKEN в .env: enabled() вернёт False,
notify()/process_outbox()/maybe_send_digests() ничего не делают. Никаких запросов к Telegram
не будет сделано, пока владелец сам не создаст бота и не впишет токен — по умолчанию сервис
не подключается ни к каким внешним сервисам.
"""
import logging
import secrets

from datetime import date, datetime

import httpx

from . import config
from .db import all_, one, run, tx

log = logging.getLogger("fligel.telegram")

# События, на которые можно подписаться, и подписи для интерфейса
EVENTS = ("new_booking", "cancellation", "conflict", "sync_error", "digest")
EVENT_LABELS = {
    "new_booking": "Новая бронь",
    "cancellation": "Отмена брони",
    "conflict": "Двойное бронирование",
    "sync_error": "Ошибка синхронизации с площадкой",
    "digest": "Утренний дайджест (заезды и выезды)",
}
LINK_CODE_TTL_MINUTES = 30
MAX_ATTEMPTS = 8  # после стольких неудачных попыток сообщение помечается как окончательно неотправленное
API_BASE = "https://api.telegram.org/bot{token}"


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


def _gen_code() -> str:
    return secrets.token_hex(4).upper()  # 8 символов 0-9A-F — легко продиктовать или скопировать


# ---------- привязка аккаунта Telegram к сотруднику ----------

def start_link(conn, account_id: str, user_id: str) -> dict:
    """Выдаёт (или перевыдаёт) код привязки для сотрудника. Код действует 30 минут:
    пользователь пишет боту «/start <код>», и чат привязывается к его учётной записи."""
    code = _gen_code()
    return one(
        conn,
        "INSERT INTO telegram_links (account_id, user_id, link_code, link_code_expires_at)"
        " VALUES (%s, %s, %s, now() + make_interval(mins => %s))"
        " ON CONFLICT (user_id) DO UPDATE SET link_code = EXCLUDED.link_code,"
        " link_code_expires_at = EXCLUDED.link_code_expires_at"
        " RETURNING link_code, link_code_expires_at",
        (account_id, user_id, code, LINK_CODE_TTL_MINUTES),
    )


def get_link(conn, user_id: str) -> dict | None:
    return one(
        conn,
        "SELECT chat_id, linked_at, link_code, link_code_expires_at, events"
        " FROM telegram_links WHERE user_id = %s",
        (user_id,),
    )


def unlink(conn, user_id: str) -> None:
    run(
        conn,
        "UPDATE telegram_links SET chat_id = NULL, linked_at = NULL, link_code = NULL,"
        " link_code_expires_at = NULL WHERE user_id = %s",
        (user_id,),
    )


def set_events(conn, account_id: str, user_id: str, events: list) -> list:
    """Какие события получает этот сотрудник. Неизвестные значения молча отбрасываются."""
    chosen = [e for e in EVENTS if e in (events or [])]
    run(
        conn,
        "INSERT INTO telegram_links (account_id, user_id, events) VALUES (%s, %s, %s)"
        " ON CONFLICT (user_id) DO UPDATE SET events = EXCLUDED.events",
        (account_id, user_id, chosen),
    )
    return chosen


def handle_start(conn, code: str, chat_id: int) -> bool:
    """Обрабатывает «/start <код>» от бота. Возвращает True, если код найден и не истёк."""
    row = one(
        conn,
        "SELECT id, account_id FROM telegram_links WHERE link_code = %s AND link_code_expires_at > now()",
        (str(code).strip().upper(),),
    )
    if not row:
        return False
    run(
        conn,
        "UPDATE telegram_links SET chat_id = %s, linked_at = now(), link_code = NULL,"
        " link_code_expires_at = NULL WHERE id = %s",
        (chat_id, row["id"]),
    )
    enqueue(conn, row["account_id"], chat_id, "Готово! Уведомления «Флигель» подключены к этому чату.")
    return True


# ---------- очередь отправки ----------

def enqueue(conn, account_id: str, chat_id: int, text: str) -> None:
    run(conn, "INSERT INTO telegram_outbox (account_id, chat_id, text) VALUES (%s, %s, %s)",
        (account_id, chat_id, text))


def notify(conn, account_id: str, event: str, text: str) -> int:
    """Ставит сообщение в очередь всем сотрудникам аккаунта, привязавшим Telegram и
    подписанным на это событие. Ничего не делает, если уведомления выключены (нет токена)."""
    if not enabled():
        return 0
    rows = all_(
        conn,
        "SELECT chat_id FROM telegram_links WHERE account_id = %s AND chat_id IS NOT NULL"
        " AND %s = ANY(events)",
        (account_id, event),
    )
    for r in rows:
        enqueue(conn, account_id, r["chat_id"], text)
    return len(rows)


def _default_send(chat_id: int, text: str) -> None:
    """Настоящая отправка через Bot API. Вызывается только если задан TELEGRAM_BOT_TOKEN
    (process_outbox проверяет enabled() до вызова). В тестах подменяется моком —
    как app.sync.fetch для календарей площадок."""
    url = API_BASE.format(token=config.TELEGRAM_BOT_TOKEN) + "/sendMessage"
    resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram ответил кодом {resp.status_code}: {resp.text[:300]}")


send_message = _default_send


def process_outbox(limit: int = 20) -> dict:
    """Отправляет накопившиеся сообщения из очереди. При сбое — повтор с растущей паузой
    (2, 4, 8… минут, не больше часа), после MAX_ATTEMPTS попыток сообщение помечается
    окончательно неотправленным (status='failed') и больше не трогается."""
    if not enabled():
        return {"sent": 0, "failed": 0}
    sent = failed = 0
    with tx() as conn:
        rows = all_(
            conn,
            "SELECT id, chat_id, text, attempts FROM telegram_outbox WHERE status = 'pending'"
            " AND next_attempt_at <= now() ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED",
            (limit,),
        )
        for row in rows:
            try:
                send_message(row["chat_id"], row["text"])
                run(conn, "UPDATE telegram_outbox SET status = 'sent', sent_at = now() WHERE id = %s", (row["id"],))
                sent += 1
            except Exception as e:
                attempts = row["attempts"] + 1
                if attempts >= MAX_ATTEMPTS:
                    run(conn, "UPDATE telegram_outbox SET status = 'failed', attempts = %s, last_error = %s"
                              " WHERE id = %s", (attempts, str(e)[:500], row["id"]))
                    failed += 1
                    log.warning("Сообщение в Telegram не отправлено после %s попыток: %s", attempts, e)
                else:
                    delay_minutes = min(2 ** attempts, 60)
                    run(conn, "UPDATE telegram_outbox SET attempts = %s, last_error = %s,"
                              " next_attempt_at = now() + make_interval(mins => %s) WHERE id = %s",
                        (attempts, str(e)[:500], delay_minutes, row["id"]))
    return {"sent": sent, "failed": failed}


# ---------- утренний дайджест ----------

def _digest_text(conn, account_id: str, today: date) -> str:
    rows = all_(
        conn,
        "SELECT b.check_in, b.check_out, b.guest_name, r.name AS room_name, p.name AS property_name"
        " FROM bookings b JOIN rooms r ON r.id = b.room_id JOIN properties p ON p.id = b.property_id"
        " WHERE b.account_id = %s AND b.status IN ('confirmed', 'pending')"
        " AND (b.check_in = %s OR b.check_out = %s) ORDER BY p.name, r.sort_order",
        (account_id, today, today),
    )
    arrivals = [r for r in rows if r["check_in"] == today]
    departures = [r for r in rows if r["check_out"] == today]

    def fmt(r: dict) -> str:
        return f"  • {r['room_name']} ({r['property_name']}) — {r['guest_name'] or 'без имени'}"

    lines = [f"Доброе утро! На сегодня, {today.strftime('%d.%m.%Y')}:"]
    lines.append(f"\nЗаезды ({len(arrivals)}):" if arrivals else "\nЗаездов нет.")
    lines += [fmt(r) for r in arrivals]
    lines.append(f"\nВыезды ({len(departures)}):" if departures else "\nВыездов нет.")
    lines += [fmt(r) for r in departures]
    return "\n".join(lines)


def maybe_send_digests(now: datetime | None = None) -> int:
    """Раз в день (не раньше TELEGRAM_DIGEST_HOUR по времени сервера) отправляет каждому
    аккаунту с подпиской на дайджест одно сообщение с сегодняшними заездами и выездами."""
    if not enabled():
        return 0
    now = now or datetime.now()
    if now.hour < config.TELEGRAM_DIGEST_HOUR:
        return 0
    today = now.date()
    sent = 0
    with tx() as conn:
        accounts = all_(
            conn,
            "SELECT DISTINCT account_id FROM telegram_links WHERE chat_id IS NOT NULL AND 'digest' = ANY(events)",
        )
        for a in accounts:
            account_id = a["account_id"]
            already = one(conn, "SELECT 1 FROM telegram_digest_log WHERE account_id = %s AND last_sent_date = %s",
                          (account_id, today))
            if already:
                continue
            notify(conn, account_id, "digest", _digest_text(conn, account_id, today))
            run(conn, "INSERT INTO telegram_digest_log (account_id, last_sent_date) VALUES (%s, %s)"
                      " ON CONFLICT (account_id) DO UPDATE SET last_sent_date = EXCLUDED.last_sent_date",
                (account_id, today))
            sent += 1
    return sent
