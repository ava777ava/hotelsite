"""Публичная демо-версия без регистрации: кнопка на лендинге выдаёт вход в песочницу (отдельный демо-аккаунт, ежедневный сброс)."""
from starlette.routing import Route

from .. import config, ratelimit
from ..auth import make_token
from ..db import one, tx
from ..errors import ApiError
from .base import Ctx, api


@api(public=True)
def start(c: Ctx):
    if not config.DEMO_ENABLED:
        raise ApiError(404, "Демо-версия не включена")
    if not ratelimit.allow(f"demo-start:{ratelimit.client_ip(c.request)}", 30, 3600):
        raise ApiError(429, "Слишком много запросов. Попробуйте через час")
    with tx() as conn:
        u = one(conn, "SELECT u.id, u.account_id FROM users u JOIN accounts a ON a.id = u.account_id WHERE a.is_demo AND a.status = 'active' AND u.role = 'owner'"
                      " ORDER BY u.created_at LIMIT 1")
    if not u:
        raise ApiError(404, "Демо-аккаунт ещё не создан (python -m app.demo)")
    return {"token": make_token(u["id"], u["account_id"], "owner")}


@api(public=True)
def status(c: Ctx):
    return {"enabled": config.DEMO_ENABLED}


routes = [
    Route("/api/demo/start", start, methods=["POST"]),
    Route("/api/demo/status", status),
]
