"""Обёртка для обработчиков API: авторизация, разбор JSON, единый формат ошибок."""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import psycopg
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from ..auth import Principal, operator_from_request, principal, verify_active
from ..db import tx
from ..errors import ApiError
from ..util import Json, body

log = logging.getLogger("fligel.api")

# В публичной демо-версии (песочнице) отключено то, что могло бы навредить другим посетителям или сервису:
# смена пароля, удаление и выгрузка аккаунта, сотрудники, подключение площадок и мессенджеров, счета, ключи API, загрузка файлов
DEMO_BLOCKED = [("POST", r"^/api/auth/change-password$"), ("POST", r"^/api/account/delete$"), ("GET", r"^/api/account/export$"),
                ("POST", r"^/api/users$"), ("DELETE", r"^/api/users/"), ("POST", r"^/api/feeds"), ("DELETE", r"^/api/feeds/"),
                ("PUT", r"^/api/channels/export-mode$"), ("POST", r"^/api/notify/"), ("POST", r"^/api/telegram/(link|unlink)$"),
                ("POST", r"^/api/billing"), ("POST", r"^/api/keys"), ("DELETE", r"^/api/keys/"), ("POST", r"^/api/webhooks"),
                ("PATCH", r"^/api/webhooks/"), ("DELETE", r"^/api/webhooks/"), ("POST", r"^/api/room-types/[^/]+/photos$"),
                ("PATCH", r"^/api/me/preferences$"), ("POST", r"^/api/bookings/[^/]+/message/email$")]


def demo_blocked(method: str, path: str) -> bool:
    import re
    return any(m == method and re.search(rx, path) for m, rx in DEMO_BLOCKED)


@dataclass
class Ctx:
    request: Request
    p: Principal | None
    data: dict = field(default_factory=dict)
    operator_id: str | None = None

    @property
    def path(self) -> dict:
        return self.request.path_params

    @property
    def q(self):
        return self.request.query_params

    @property
    def account_id(self) -> str:
        assert self.p is not None
        return self.p.account_id


def api(min_role: str = "housekeeper", public: bool = False) -> Callable:
    """Декоратор: обработчик получает Ctx и выполняется в пуле потоков (работа с БД синхронная)."""

    def wrap(fn: Callable[[Ctx], Any]):
        def run(ctx: Ctx) -> Any:
            if ctx.p is not None:
                # Токен может быть ещё действителен, а сотрудника уже удалили или
                # аккаунт приостановили — проверяем это на каждый запрос, а не только при входе.
                with tx() as conn:
                    state = verify_active(conn, ctx.p)
                if state["is_demo"] and demo_blocked(ctx.request.method, ctx.request.url.path):
                    raise ApiError(403, "В демо-версии это отключено. Зарегистрируйтесь — и всё заработает на ваших данных")
            return fn(ctx)

        async def handler(request: Request) -> Response:
            try:
                p = None if public else principal(request, min_role)
                data = await body(request) if request.method in ("POST", "PUT", "PATCH") else {}
                result = await run_in_threadpool(run, Ctx(request, p, data))
                if isinstance(result, Response):
                    return result
                return Json(result if result is not None else {"ok": True})
            except ApiError as e:
                return Json({"error": e.message, **e.extra}, status_code=e.status)
            except psycopg.errors.ExclusionViolation:
                return Json({"error": "Номер уже занят на эти даты", "code": "overlap"}, status_code=409)
            except psycopg.errors.UniqueViolation:
                return Json({"error": "Такая запись уже существует"}, status_code=409)
            except Exception:
                log.exception("Необработанная ошибка в %s %s", request.method, request.url.path)
                return Json({"error": "Внутренняя ошибка сервера"}, status_code=500)

        handler.__name__ = fn.__name__
        handler.fn = fn  # «голый» обработчик без проверки токена — для публичного API (ключи вместо токена сотрудника)
        return handler

    return wrap


def op_api(public: bool = False) -> Callable:
    """Как api(), но для панели оператора сервиса: свой токен (kind=operator), без аккаунта клиента."""

    def wrap(fn: Callable[[Ctx], Any]):
        async def handler(request: Request) -> Response:
            try:
                op_id = None if public else operator_from_request(request)
                data = await body(request) if request.method in ("POST", "PUT", "PATCH") else {}
                result = await run_in_threadpool(fn, Ctx(request, None, data, op_id))
                if isinstance(result, Response):
                    return result
                return Json(result if result is not None else {"ok": True})
            except ApiError as e:
                return Json({"error": e.message, **e.extra}, status_code=e.status)
            except psycopg.errors.UniqueViolation:
                return Json({"error": "Такая запись уже существует"}, status_code=409)
            except Exception:
                log.exception("Необработанная ошибка в %s %s", request.method, request.url.path)
                return Json({"error": "Внутренняя ошибка сервера"}, status_code=500)

        handler.__name__ = fn.__name__
        return handler

    return wrap


def v1(scope: str = "read") -> Callable:
    """Публичный API для клиентов: доступ по ключу (Authorization: Bearer flg_…), лимит запросов, у ключа права read или write."""
    from .. import apikeys, config, ratelimit

    def wrap(fn: Callable[[Ctx], Any]):
        async def handler(request: Request) -> Response:
            try:
                key = await run_in_threadpool(apikeys.authenticate, request.headers.get("authorization", ""))
                if scope == "write" and key["scope"] != "write":
                    raise ApiError(403, "У этого ключа права только на чтение. Создайте ключ с правом записи")
                if not ratelimit.allow(f"apikey:{key['id']}", config.API_REQUESTS_PER_MINUTE, 60):
                    raise ApiError(429, f"Слишком много запросов: не больше {config.API_REQUESTS_PER_MINUTE} в минуту")
                data = await body(request) if request.method in ("POST", "PUT", "PATCH") else {}
                p = Principal(user_id=None, account_id=str(key["account_id"]), role="manager")
                result = await run_in_threadpool(fn, Ctx(request, p, data))
                if isinstance(result, Response):
                    return result
                return Json(result if result is not None else {"ok": True})
            except ApiError as e:
                return Json({"error": e.message, **e.extra}, status_code=e.status)
            except psycopg.errors.ExclusionViolation:
                return Json({"error": "Номер уже занят на эти даты", "code": "overlap"}, status_code=409)
            except Exception:
                log.exception("Необработанная ошибка в %s %s", request.method, request.url.path)
                return Json({"error": "Внутренняя ошибка сервера"}, status_code=500)

        handler.__name__ = fn.__name__
        return handler

    return wrap
