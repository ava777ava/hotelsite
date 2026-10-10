"""Уведомления: настройка каналов (Telegram, MAX) для сотрудника, колокольчик в интерфейсе,
общий журнал действий для владельца и вебхук бота MAX."""
from datetime import datetime
from decimal import Decimal

from starlette.routing import Route

from .. import config, maxbot, notify, telegram
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import parse_uuid
from .base import Ctx, api


def _channel_status(conn, name: str, user_id: str) -> dict:
    mod = notify.CHANNELS[name]
    link = mod.get_link(conn, user_id)
    out = {"name": name, "label": notify.CHANNEL_LABELS[name], "server_enabled": mod.enabled(),
           "linked": bool(link and link["chat_id"]), "linked_at": link["linked_at"] if link else None,
           "pending_code": link["link_code"] if link else None,
           "pending_code_expires_at": link["link_code_expires_at"] if link else None,
           "user_enabled": link["enabled"] if link else True}
    if name == "max":
        out["deep_link"] = maxbot.deep_link(link["link_code"]) if link and link["link_code"] else None
    return out


def _status(conn, c: Ctx) -> dict:
    tg = telegram.get_link(conn, c.p.user_id)
    events = tg["events"] if tg else list(telegram.EVENTS)
    return {"channels": [_channel_status(conn, n, c.p.user_id) for n in notify.CHANNELS], "events": events,
            "available_events": [{"key": k, "label": telegram.EVENT_LABELS[k]} for k in telegram.EVENTS]}


@api("manager")
def status(c: Ctx):
    with tx() as conn:
        return _status(conn, c)


def _channel(name: str):
    if name not in notify.CHANNELS:
        raise ApiError(404, "Такого канала нет")
    return notify.CHANNELS[name]


@api("manager")
def link(c: Ctx):
    mod = _channel(c.path["channel"])
    if not mod.enabled():
        raise ApiError(422, f"{notify.CHANNEL_LABELS[c.path['channel']]}-уведомления не настроены на сервере (нет токена бота)")
    with tx() as conn:
        mod.start_link(conn, c.account_id, c.p.user_id)
        return _status(conn, c)


@api("manager")
def unlink(c: Ctx):
    mod = _channel(c.path["channel"])
    with tx() as conn:
        mod.unlink(conn, c.p.user_id)
        return _status(conn, c)


@api("manager")
def settings(c: Ctx):
    """Какие события и в какие мессенджеры получает этот сотрудник (по умолчанию — во все подключённые)."""
    events = c.data.get("events")
    if not isinstance(events, list):
        raise ApiError(422, "events должен быть списком")
    flags = c.data.get("channels") or {}
    with tx() as conn:
        telegram.set_events(conn, c.account_id, c.p.user_id, events)
        run(conn, "UPDATE telegram_links SET enabled = %s WHERE user_id = %s", (bool(flags.get("telegram", True)), c.p.user_id))
        maxbot.set_events(conn, c.account_id, c.p.user_id, events, bool(flags.get("max", True)))
        return _status(conn, c)


@api(public=True)
def max_webhook(c: Ctx):
    """Сюда MAX присылает события бота («Начать» по ссылке привязки, сообщения). Секрет — в заголовке."""
    if config.MAX_WEBHOOK_SECRET and c.request.headers.get("x-max-bot-api-secret", "") != config.MAX_WEBHOOK_SECRET:
        raise ApiError(403, "Неверный секрет вебхука")
    if not maxbot.enabled():
        return {"ok": True}
    chat_id, code = maxbot.parse_update(c.data)
    if not chat_id or not code:
        return {"ok": True}
    with tx() as conn:
        linked = maxbot.handle_start(conn, code, int(chat_id))
    return {"ok": True, "linked": linked}


# ---------- колокольчик ----------
@api("manager")
def bell(c: Ctx):
    with tx() as conn:
        seen = one(conn, "SELECT notifications_seen_at AS t FROM users WHERE id = %s", (c.p.user_id,))["t"]
        rows = all_(conn, "SELECT id, kind, text, link, created_at, created_at > %s AS unread FROM notifications"
                          " WHERE account_id = %s ORDER BY created_at DESC LIMIT 30", (seen, c.account_id))
    return {"items": rows, "unread": sum(1 for r in rows if r["unread"])}


@api("manager")
def bell_seen(c: Ctx):
    with tx() as conn:
        run(conn, "UPDATE users SET notifications_seen_at = now() WHERE id = %s", (c.p.user_id,))
    return {"ok": True}


# ---------- журнал действий ----------
BOOKING_ACTIONS = {"created": "Создана бронь", "updated": "Изменена бронь", "cancelled": "Отменена бронь",
                   "payment": "Платёж по брони", "message": "Сообщение гостю"}


@api("owner")
def audit_feed(c: Ctx):
    """Что происходило в аккаунте: кто, что и когда (брони, платежи, настройки, доступы). Новое сверху."""
    try:
        before = datetime.fromisoformat(c.q["before"]) if c.q.get("before") else None
    except ValueError:
        raise ApiError(422, "Неверная дата")
    with tx() as conn:
        a = all_(conn, "SELECT l.created_at, coalesce(u.name, 'Система') AS who, l.summary AS text, 'settings' AS kind"
                       " FROM audit_log l LEFT JOIN users u ON u.id = l.user_id WHERE l.account_id = %s"
                       " AND (%s::timestamptz IS NULL OR l.created_at < %s) ORDER BY l.created_at DESC LIMIT 100",
                 (c.account_id, before, before))
        b = all_(conn, "SELECT l.created_at, coalesce(u.name, 'Система') AS who, l.action, l.details,"
                       " coalesce(nullif(bk.guest_name, ''), 'без имени') AS guest, r.name AS room"
                       " FROM booking_log l LEFT JOIN users u ON u.id = l.user_id JOIN bookings bk ON bk.id = l.booking_id"
                       " JOIN rooms r ON r.id = bk.room_id WHERE l.account_id = %s"
                       " AND (%s::timestamptz IS NULL OR l.created_at < %s) ORDER BY l.created_at DESC LIMIT 100",
                 (c.account_id, before, before))
    items = list(a)
    for x in b:
        d = x["details"] or {}
        what = d.get("summary") or "; ".join(f"{ch['field']}: {ch['from']} → {ch['to']}" for ch in d.get("changes", [])) or d.get("reason") or ""
        items.append({"created_at": x["created_at"], "who": x["who"], "kind": "booking",
                      "text": f"{BOOKING_ACTIONS.get(x['action'], x['action'])} «{x['guest']}», номер {x['room']}" + (f": {what}" if what else "")})
    items.sort(key=lambda i: i["created_at"], reverse=True)
    return {"items": items[:100], "more": len(items) > 100}


routes = [
    Route("/api/notify/status", status),
    Route("/api/notify/settings", settings, methods=["PUT"]),
    Route("/api/notify/{channel}/link", link, methods=["POST"]),
    Route("/api/notify/{channel}/unlink", unlink, methods=["POST"]),
    Route("/api/max/webhook", max_webhook, methods=["POST"]),
    Route("/api/notifications", bell),
    Route("/api/notifications/seen", bell_seen, methods=["POST"]),
    Route("/api/audit", audit_feed),
]
