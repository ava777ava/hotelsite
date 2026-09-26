"""Площадки: ссылки календарей, ручной запуск синхронизации, конфликты, экспорт iCal.

Календарь подключается либо к номеру (квартиры, Авито, Суточно), либо к категории
(гостиница в Яндекс Путешествиях: одна ссылка на категорию номеров).
"""
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from .. import config, ical
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..sync import CHANNEL_LABELS, export_events, export_type_events, sync_feed
from ..util import parse_uuid
from .base import Ctx, api
from .common import selected_property

CHANNELS = ("avito", "yandex", "sutochno", "ostrovok", "other")
# По умолчанию: Яндекс для гостиниц работает с категориями, остальные — с отдельными номерами
DEFAULT_LEVEL = {"avito": "room", "yandex": "type", "sutochno": "room", "ostrovok": "type", "other": "room"}


def export_url(token: str, channel: str, level: str = "room") -> str:
    prefix = "/ical/type" if level == "type" else "/ical"
    return f"{config.PUBLIC_BASE_URL}{prefix}/{token}/{channel}.ics"


FEED_COLS = ("id, room_id, room_type_id, channel, url, enabled, last_synced_at, last_status, last_error,"
             " next_run_at")


@api("manager")
def channels_overview(c: Ctx):
    """Номера и категории выбранного объекта: ссылки экспорта для каждой площадки и подключённые календари импорта."""
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.q.get("property_id"))
        types = all_(
            conn,
            "SELECT rt.id, rt.name, rt.ical_token, (SELECT count(*) FROM rooms r WHERE r.room_type_id = rt.id)"
            " AS rooms_count FROM room_types rt WHERE rt.property_id = %s ORDER BY rt.sort_order, rt.name",
            (prop["id"],),
        )
        rooms = all_(
            conn,
            "SELECT r.id, r.name, r.ical_token, rt.name AS room_type FROM rooms r"
            " JOIN room_types rt ON rt.id = r.room_type_id WHERE r.property_id = %s"
            " ORDER BY rt.sort_order, r.sort_order, r.name",
            (prop["id"],),
        )
        feeds = all_(conn, f"SELECT {FEED_COLS} FROM ical_feeds WHERE account_id = %s", (c.account_id,))
        exports = all_(
            conn,
            "SELECT e.target_id, e.channel, e.last_fetched_at FROM ical_exports e WHERE e.target_id IN ("
            " SELECT id FROM rooms WHERE property_id = %s UNION SELECT id FROM room_types WHERE property_id = %s)",
            (prop["id"], prop["id"]),
        )
        modes = all_(
            conn,
            "SELECT s.room_type_id, s.channel, s.mode FROM ical_export_settings s"
            " JOIN room_types rt ON rt.id = s.room_type_id WHERE rt.property_id = %s",
            (prop["id"],),
        )
    exp_map = {(str(e["target_id"]), e["channel"]): e["last_fetched_at"] for e in exports}
    mode_map = {(str(m["room_type_id"]), m["channel"]): m["mode"] for m in modes}

    def attach(items: list[dict], level: str) -> None:
        key = "room_id" if level == "room" else "room_type_id"
        for it in items:
            iid = str(it["id"])
            it["channels"] = {}
            for ch in CHANNELS:
                it["channels"][ch] = {
                    "export_url": export_url(it["ical_token"], ch, level),
                    "export_last_fetched_at": exp_map.get((iid, ch)),
                    "feed": next((f for f in feeds if str(f[key] or "") == iid and f["channel"] == ch), None),
                }
                if level == "type":
                    it["channels"][ch]["export_mode"] = mode_map.get((iid, ch), "per_booking")
            del it["ical_token"]

    attach(rooms, "room")
    attach(types, "type")
    # Какой уровень показывать для площадки: где уже есть подключения, иначе по умолчанию
    levels = {}
    for ch in CHANNELS:
        if any(t["channels"][ch]["feed"] for t in types):
            levels[ch] = "type"
        elif any(r["channels"][ch]["feed"] for r in rooms):
            levels[ch] = "room"
        else:
            levels[ch] = DEFAULT_LEVEL[ch]
    return {"rooms": rooms, "room_types": types, "levels": levels, "labels": CHANNEL_LABELS,
            "sync_interval_minutes": config.SYNC_INTERVAL_MINUTES}


def _check_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError(422, "Вставьте полную ссылку на календарь, начиная с https://", {"field": "url"})
    host = parsed.hostname or ""
    if (host in ("localhost", "0.0.0.0") or host.startswith("127.") or host.startswith("10.")
            or host.startswith("192.168.") or host.startswith("169.254.")) \
            and not config.PUBLIC_BASE_URL.startswith("http://localhost"):
        raise ApiError(422, "Ссылка должна вести на сайт площадки", {"field": "url"})
    return url


@api("manager")
def save_feed(c: Ctx):
    """Сохраняет ссылку календаря площадки для номера или категории (создать или заменить)."""
    channel = c.data.get("channel")
    if channel not in CHANNELS:
        raise ApiError(422, "Неизвестная площадка")
    url = _check_url(str(c.data.get("url") or ""))
    room_id = parse_uuid(c.data["room_id"], "Номер") if c.data.get("room_id") else None
    type_id = parse_uuid(c.data["room_type_id"], "Категория") if c.data.get("room_type_id") else None
    if bool(room_id) == bool(type_id):
        raise ApiError(422, "Укажите номер или категорию")
    with tx() as conn:
        if room_id:
            if not one(conn, "SELECT 1 FROM rooms WHERE id = %s AND account_id = %s", (room_id, c.account_id)):
                raise ApiError(404, "Номер не найден")
            # одна площадка — один уровень: нельзя подключить и номер, и его категорию
            if one(conn, "SELECT 1 FROM ical_feeds f JOIN rooms r ON r.room_type_id = f.room_type_id"
                         " WHERE r.id = %s AND f.channel = %s", (room_id, channel)):
                raise ApiError(409, "Для этой площадки уже подключён календарь всей категории")
        else:
            if not one(conn, "SELECT 1 FROM room_types WHERE id = %s AND account_id = %s", (type_id, c.account_id)):
                raise ApiError(404, "Категория не найдена")
            if one(conn, "SELECT 1 FROM ical_feeds f JOIN rooms r ON r.id = f.room_id"
                         " WHERE r.room_type_id = %s AND f.channel = %s", (type_id, channel)):
                raise ApiError(409, "Для этой площадки уже подключены календари отдельных номеров этой категории")
        existing = one(
            conn,
            "SELECT id FROM ical_feeds WHERE channel = %s AND (room_id = %s OR room_type_id = %s)",
            (channel, room_id, type_id),
        )
        if existing:
            run(conn, "UPDATE ical_feeds SET url = %s, enabled = true, next_run_at = now(), last_status = NULL,"
                      " last_error = NULL WHERE id = %s", (url, existing["id"]))
            feed_id = existing["id"]
        else:
            feed_id = one(conn, "INSERT INTO ical_feeds (account_id, room_id, room_type_id, channel, url)"
                                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                          (c.account_id, room_id, type_id, channel, url))["id"]
    # Сразу проверяем ссылку, чтобы пользователь увидел результат
    res = sync_feed(feed_id)
    return {"id": feed_id, "status": res.status, "message": res.message, "added": res.added,
            "conflicts": res.conflicts}


@api("manager")
def set_export_mode(c: Ctx):
    type_id = parse_uuid(c.data.get("room_type_id"), "Категория")
    channel = c.data.get("channel")
    mode = c.data.get("mode")
    if channel not in CHANNELS or mode not in ("per_booking", "sold_out"):
        raise ApiError(422, "Неверные параметры")
    with tx() as conn:
        if not one(conn, "SELECT 1 FROM room_types WHERE id = %s AND account_id = %s", (type_id, c.account_id)):
            raise ApiError(404, "Категория не найдена")
        run(conn, "INSERT INTO ical_export_settings (room_type_id, channel, mode) VALUES (%s, %s, %s)"
                  " ON CONFLICT (room_type_id, channel) DO UPDATE SET mode = EXCLUDED.mode", (type_id, channel, mode))


@api("manager")
def delete_feed(c: Ctx):
    fid = parse_uuid(c.path["id"])
    remove_bookings = c.q.get("remove_bookings") == "1"
    with tx() as conn:
        feed = one(conn, "SELECT id FROM ical_feeds WHERE id = %s AND account_id = %s", (fid, c.account_id))
        if not feed:
            raise ApiError(404, "Календарь не найден")
        if remove_bookings:
            run(conn, "UPDATE bookings SET status = 'cancelled', updated_at = now()"
                      " WHERE feed_id = %s AND check_out >= current_date", (fid,))
        run(conn, "DELETE FROM ical_feeds WHERE id = %s", (fid,))


@api("manager")
def sync_now(c: Ctx):
    fid = parse_uuid(c.path["id"])
    with tx() as conn:
        if not one(conn, "SELECT 1 FROM ical_feeds WHERE id = %s AND account_id = %s", (fid, c.account_id)):
            raise ApiError(404, "Календарь не найден")
    res = sync_feed(fid)
    return {"status": res.status, "message": res.message, "added": res.added, "updated": res.updated,
            "removed": res.removed, "conflicts": res.conflicts}


@api("manager")
def sync_all(c: Ctx):
    with tx() as conn:
        ids = [r["id"] for r in all_(conn, "SELECT id FROM ical_feeds WHERE account_id = %s AND enabled",
                                     (c.account_id,))]
    total = {"feeds": len(ids), "errors": 0, "added": 0, "removed": 0, "conflicts": 0}
    for fid in ids:
        res = sync_feed(fid)
        total["errors"] += res.status != "ok"
        total["added"] += res.added
        total["removed"] += res.removed
        total["conflicts"] += res.conflicts
    return total


@api()
def list_conflicts(c: Ctx):
    with tx() as conn:
        return all_(
            conn,
            "SELECT sc.id, sc.check_in, sc.check_out, sc.summary, sc.detected_at, f.channel,"
            " coalesce('Номер ' || r.name, 'Категория ' || rt.name) AS target_name, sc.room_id, sc.room_type_id"
            " FROM sync_conflicts sc LEFT JOIN rooms r ON r.id = sc.room_id"
            " LEFT JOIN room_types rt ON rt.id = sc.room_type_id LEFT JOIN ical_feeds f ON f.id = sc.feed_id"
            " WHERE sc.account_id = %s AND NOT sc.resolved ORDER BY sc.check_in",
            (c.account_id,),
        )


@api("manager")
def resolve_conflict(c: Ctx):
    with tx() as conn:
        n = run(conn, "UPDATE sync_conflicts SET resolved = true WHERE id = %s AND account_id = %s",
                (parse_uuid(c.path["id"]), c.account_id))
    if not n:
        raise ApiError(404, "Конфликт не найден")


@api("manager")
def sync_log(c: Ctx):
    with tx() as conn:
        return all_(
            conn,
            "SELECT l.started_at, l.status, l.added, l.updated, l.removed, l.conflicts, l.message, f.channel,"
            " coalesce(r.name, rt.name) AS target_name FROM sync_log l JOIN ical_feeds f ON f.id = l.feed_id"
            " LEFT JOIN rooms r ON r.id = f.room_id LEFT JOIN room_types rt ON rt.id = f.room_type_id"
            " WHERE l.account_id = %s ORDER BY l.started_at DESC LIMIT 100",
            (c.account_id,),
        )


def _mark_fetched(conn, target_id, channel: str) -> None:
    run(conn, "INSERT INTO ical_exports (target_id, channel) VALUES (%s, %s)"
              " ON CONFLICT (target_id, channel) DO UPDATE SET last_fetched_at = now(),"
              " fetch_count = ical_exports.fetch_count + 1", (target_id, channel))


def _calendar(name: str, events) -> Response:
    return Response(ical.generate(name, events), media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "no-store"})


def ical_export(request: Request) -> Response:
    """Публичная ссылка календаря номера для площадки. Секрет — токен в адресе."""
    channel = request.path_params["channel"]
    if channel not in CHANNELS:
        return PlainTextResponse("Not found", status_code=404)
    with tx() as conn:
        room = one(conn, "SELECT r.*, p.name AS property_name FROM rooms r JOIN properties p ON p.id = r.property_id"
                         " JOIN accounts a ON a.id = r.account_id WHERE r.ical_token = %s AND a.status = 'active'",
                   (request.path_params["token"],))
        if not room:
            return PlainTextResponse("Not found", status_code=404)
        events = export_events(conn, room, channel)
        _mark_fetched(conn, room["id"], channel)
    return _calendar(f"{room['property_name']} — {room['name']}", events)


def ical_type_export(request: Request) -> Response:
    """Публичная ссылка календаря категории номеров для площадки."""
    channel = request.path_params["channel"]
    if channel not in CHANNELS:
        return PlainTextResponse("Not found", status_code=404)
    with tx() as conn:
        rt = one(conn, "SELECT rt.*, p.name AS property_name FROM room_types rt"
                       " JOIN properties p ON p.id = rt.property_id JOIN accounts a ON a.id = rt.account_id"
                       " WHERE rt.ical_token = %s AND a.status = 'active'", (request.path_params["token"],))
        if not rt:
            return PlainTextResponse("Not found", status_code=404)
        mode = one(conn, "SELECT mode FROM ical_export_settings WHERE room_type_id = %s AND channel = %s",
                   (rt["id"], channel))
        events = export_type_events(conn, rt, channel, mode["mode"] if mode else "per_booking")
        _mark_fetched(conn, rt["id"], channel)
    return _calendar(f"{rt['property_name']} — {rt['name']}", events)


routes = [
    Route("/api/channels", channels_overview),
    Route("/api/channels/export-mode", set_export_mode, methods=["PUT"]),
    Route("/api/feeds", save_feed, methods=["POST"]),
    Route("/api/feeds/sync-all", sync_all, methods=["POST"]),
    Route("/api/feeds/{id}", delete_feed, methods=["DELETE"]),
    Route("/api/feeds/{id}/sync", sync_now, methods=["POST"]),
    Route("/api/conflicts", list_conflicts),
    Route("/api/conflicts/{id}/resolve", resolve_conflict, methods=["POST"]),
    Route("/api/sync-log", sync_log),
    Route("/ical/type/{token}/{channel}.ics", ical_type_export),
    Route("/ical/{token}/{channel}.ics", ical_export),
]
