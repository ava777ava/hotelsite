"""Состояние синхронизации площадок и режим отладки (сырые календари)."""
from starlette.routing import Route

from .. import audit, syncdebug
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..sync import CHANNEL_LABELS
from ..util import parse_uuid
from .base import Ctx, api


@api("manager")
def state(c: Ctx):
    with tx() as conn:
        rows = syncdebug.state(conn, c.account_id)
        debug = syncdebug.debug_enabled(conn, c.account_id)
    for r in rows:
        r["channel_label"] = CHANNEL_LABELS.get(r["channel"], r["channel"])
    return {"items": rows, "debug": debug, "stale_hours": syncdebug.STALE_EXPORT_HOURS, "keep": syncdebug.SNAPSHOTS_KEEP,
            "keep_days": syncdebug.SNAPSHOTS_DAYS, "stale": sum(1 for r in rows if r["export_stale"])}


@api("owner")
def set_debug(c: Ctx):
    enabled = bool(c.data.get("enabled"))
    with tx() as conn:
        run(conn, "UPDATE accounts SET sync_debug = %s WHERE id = %s", (enabled, c.account_id))
        if not enabled:   # выключили — сразу удаляем накопленное (в календарях бывают имена гостей)
            run(conn, "DELETE FROM ical_snapshots WHERE account_id = %s", (c.account_id,))
        audit.record(conn, c.account_id, c.p.user_id, "sync_debug", "Режим отладки площадок " + ("включён" if enabled else "выключен (сохранённые календари удалены)"))
    return {"debug": enabled}


@api("owner")
def snapshots(c: Ctx):
    """Список сохранённых календарей: kind=received&feed_id=… (от площадки) или kind=served&target_id=…&channel=… (наш отданный)."""
    kind = c.q.get("kind")
    if kind not in ("received", "served"):
        raise ApiError(422, "Укажите, какие календари показать: полученные от площадки или отданные ей")
    with tx() as conn:
        if kind == "received":
            where, params = "kind = 'received' AND feed_id = %s", (parse_uuid(c.q.get("feed_id"), "Календарь"),)
        else:
            if c.q.get("channel") not in CHANNEL_LABELS:
                raise ApiError(422, "Неизвестная площадка")
            where, params = "kind = 'served' AND target_id = %s AND channel = %s", (parse_uuid(c.q.get("target_id"), "Номер или категория"), c.q["channel"])
        return {"items": all_(conn, "SELECT id, kind, channel, size, events, status, note, user_agent, created_at, last_seen_at, seen_count"
                                    f" FROM ical_snapshots WHERE account_id = %s AND {where} ORDER BY created_at DESC, id DESC",
                              (c.account_id, *params))}


@api("owner")
def snapshot(c: Ctx):
    try:
        sid = int(c.path["id"])
    except ValueError:
        raise ApiError(404, "Календарь не найден")
    with tx() as conn:
        row = one(conn, "SELECT id, kind, channel, body, size, events, status, note, user_agent, created_at, last_seen_at, seen_count"
                        " FROM ical_snapshots WHERE id = %s AND account_id = %s", (sid, c.account_id))
    if not row:
        raise ApiError(404, "Календарь не найден")
    return row


routes = [
    Route("/api/sync/state", state),
    Route("/api/sync/debug", set_debug, methods=["PUT"]),
    Route("/api/sync/snapshots", snapshots),
    Route("/api/sync/snapshots/{id}", snapshot),
]
