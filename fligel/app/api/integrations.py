"""Интеграции для владельца: ключи публичного API и вебхуки (настройка в интерфейсе)."""
import secrets

from starlette.routing import Route

from .. import apikeys, audit, webhooks
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import parse_uuid, req_str
from .base import Ctx, api

MAX_KEYS, MAX_HOOKS = 20, 10


@api("owner")
def overview(c: Ctx):
    with tx() as conn:
        keys = all_(conn, "SELECT id, name, prefix, scope, created_at, last_used_at, revoked_at FROM api_keys WHERE account_id = %s ORDER BY created_at DESC", (c.account_id,))
        hooks = all_(conn, "SELECT id, url, secret, events, enabled, last_status, last_delivery_at, created_at FROM webhooks WHERE account_id = %s ORDER BY created_at", (c.account_id,))
    return {"keys": keys, "webhooks": hooks, "events": list(webhooks.EVENTS)}


@api("owner")
def key_create(c: Ctx):
    scope = c.data.get("scope") or "read"
    if scope not in ("read", "write"):
        raise ApiError(422, "Права ключа: read или write")
    with tx() as conn:
        if one(conn, "SELECT count(*) AS n FROM api_keys WHERE account_id = %s AND revoked_at IS NULL", (c.account_id,))["n"] >= MAX_KEYS:
            raise ApiError(422, f"Слишком много ключей (максимум {MAX_KEYS}) — отзовите ненужные")
        k = apikeys.create(conn, c.account_id, req_str(c.data, "name", "Название ключа", 80), scope, c.p.user_id)
        audit.record(conn, c.account_id, c.p.user_id, "api_key_created", f"Создан ключ API «{k['name']}» ({scope})", "api_key", k["id"])
    return k   # ключ виден только в этом ответе


@api("owner")
def key_revoke(c: Ctx):
    with tx() as conn:
        k = one(conn, "UPDATE api_keys SET revoked_at = now() WHERE id = %s AND account_id = %s AND revoked_at IS NULL RETURNING name",
                (parse_uuid(c.path["id"], "Ключ"), c.account_id))
        if not k:
            raise ApiError(404, "Ключ не найден")
        audit.record(conn, c.account_id, c.p.user_id, "api_key_revoked", f"Отозван ключ API «{k['name']}»")
    return {"ok": True}


def _events(raw) -> list[str]:
    ev = raw if isinstance(raw, list) and raw else list(webhooks.EVENTS)
    bad = [e for e in ev if e not in webhooks.EVENTS]
    if bad:
        raise ApiError(422, "Неизвестное событие: " + ", ".join(map(str, bad)))
    return list(dict.fromkeys(ev))


@api("owner")
def hook_create(c: Ctx):
    url = webhooks.check_url(c.data.get("url"))
    with tx() as conn:
        if one(conn, "SELECT count(*) AS n FROM webhooks WHERE account_id = %s", (c.account_id,))["n"] >= MAX_HOOKS:
            raise ApiError(422, f"Слишком много вебхуков (максимум {MAX_HOOKS})")
        row = one(conn, "INSERT INTO webhooks (account_id, url, secret, events) VALUES (%s, %s, %s, %s) RETURNING id, url, secret, events, enabled",
                  (c.account_id, url, "whsec_" + secrets.token_urlsafe(24), _events(c.data.get("events"))))
        audit.record(conn, c.account_id, c.p.user_id, "webhook_created", f"Добавлен вебхук {url}", "webhook", row["id"])
    return row


@api("owner")
def hook_update(c: Ctx):
    hid = parse_uuid(c.path["id"], "Вебхук")
    with tx() as conn:
        cur = one(conn, "SELECT * FROM webhooks WHERE id = %s AND account_id = %s FOR UPDATE", (hid, c.account_id))
        if not cur:
            raise ApiError(404, "Вебхук не найден")
        url = webhooks.check_url(c.data["url"]) if "url" in c.data else cur["url"]
        events = _events(c.data["events"]) if "events" in c.data else cur["events"]
        enabled = bool(c.data["enabled"]) if "enabled" in c.data else cur["enabled"]
        return one(conn, "UPDATE webhooks SET url = %s, events = %s, enabled = %s WHERE id = %s RETURNING id, url, secret, events, enabled", (url, events, enabled, hid))


@api("owner")
def hook_delete(c: Ctx):
    with tx() as conn:
        if not run(conn, "DELETE FROM webhooks WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Вебхук"), c.account_id)):
            raise ApiError(404, "Вебхук не найден")
    return {"ok": True}


@api("owner")
def hook_test(c: Ctx):
    """Тестовое событие booking.test — чтобы проверить адрес и подпись, не создавая бронь."""
    with tx() as conn:
        h = one(conn, "SELECT id FROM webhooks WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Вебхук"), c.account_id))
        if not h:
            raise ApiError(404, "Вебхук не найден")
        run(conn, "INSERT INTO webhook_deliveries (account_id, webhook_id, event, payload) VALUES (%s, %s, 'booking.test', %s::jsonb)",
            (c.account_id, h["id"], '{"event": "booking.test", "data": {"message": "Проверка вебхука из Флигеля"}}'))
    return {"ok": True, "note": "Тестовое событие поставлено в очередь — оно уйдёт в течение минуты"}


@api("owner")
def hook_deliveries(c: Ctx):
    with tx() as conn:
        h = one(conn, "SELECT id FROM webhooks WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Вебхук"), c.account_id))
        if not h:
            raise ApiError(404, "Вебхук не найден")
        return {"items": all_(conn, "SELECT id, event, status, attempts, last_error, created_at, sent_at FROM webhook_deliveries WHERE webhook_id = %s ORDER BY created_at DESC LIMIT 20", (h["id"],))}


routes = [
    Route("/api/integrations", overview),
    Route("/api/keys", key_create, methods=["POST"]),
    Route("/api/keys/{id}", key_revoke, methods=["DELETE"]),
    Route("/api/webhooks", hook_create, methods=["POST"]),
    Route("/api/webhooks/{id}", hook_update, methods=["PATCH"]),
    Route("/api/webhooks/{id}", hook_delete, methods=["DELETE"]),
    Route("/api/webhooks/{id}/test", hook_test, methods=["POST"]),
    Route("/api/webhooks/{id}/deliveries", hook_deliveries),
]
