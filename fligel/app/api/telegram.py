"""Настройки Telegram-уведомлений: привязка личного чата сотрудника к боту, выбор событий,
и приём вебхука от Telegram (когда сотрудник пишет боту «/start <код>»)."""
from starlette.routing import Route

from .. import config, telegram
from ..db import tx
from ..errors import ApiError
from .base import Ctx, api


def _status(conn, c: Ctx) -> dict:
    link = telegram.get_link(conn, c.p.user_id)
    events = link["events"] if link else list(telegram.EVENTS)
    return {
        "enabled": telegram.enabled(),
        "linked": bool(link and link["chat_id"]),
        "linked_at": link["linked_at"] if link else None,
        "pending_code": link["link_code"] if link else None,
        "pending_code_expires_at": link["link_code_expires_at"] if link else None,
        "events": events,
        "available_events": [{"key": k, "label": telegram.EVENT_LABELS[k]} for k in telegram.EVENTS],
    }


@api("manager")
def status(c: Ctx):
    with tx() as conn:
        return _status(conn, c)


@api("manager")
def link(c: Ctx):
    if not telegram.enabled():
        raise ApiError(422, "Telegram-уведомления не настроены на сервере (нет токена бота)")
    with tx() as conn:
        telegram.start_link(conn, c.account_id, c.p.user_id)
        return _status(conn, c)


@api("manager")
def unlink(c: Ctx):
    with tx() as conn:
        telegram.unlink(conn, c.p.user_id)
        return _status(conn, c)


@api("manager")
def set_events(c: Ctx):
    events = c.data.get("events")
    if not isinstance(events, list):
        raise ApiError(422, "events должен быть списком")
    with tx() as conn:
        telegram.set_events(conn, c.account_id, c.p.user_id, events)
        return _status(conn, c)


@api(public=True)
def webhook(c: Ctx):
    """Сюда Telegram присылает обновления бота. Секрет проверяется заголовком, который
    Telegram возвращает нам же (задаётся при подключении вебхука — см. .env.example)."""
    if config.TELEGRAM_WEBHOOK_SECRET:
        got = c.request.headers.get("x-telegram-bot-api-secret-token", "")
        if got != config.TELEGRAM_WEBHOOK_SECRET:
            raise ApiError(403, "Неверный секрет вебхука")
    if not telegram.enabled():
        return {"ok": True}
    msg = c.data.get("message") or {}
    text = str(msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id or not text.startswith("/start"):
        return {"ok": True}
    parts = text.split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""
    if not code:
        return {"ok": True}
    with tx() as conn:
        linked = telegram.handle_start(conn, code, int(chat_id))
    return {"ok": True, "linked": linked}


routes = [
    Route("/api/telegram/status", status),
    Route("/api/telegram/link", link, methods=["POST"]),
    Route("/api/telegram/unlink", unlink, methods=["POST"]),
    Route("/api/telegram/events", set_events, methods=["PUT"]),
    Route("/api/telegram/webhook", webhook, methods=["POST"]),
]
