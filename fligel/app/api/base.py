"""Обёртка для обработчиков API: авторизация, разбор JSON, единый формат ошибок."""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import psycopg
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from ..auth import Principal, principal
from ..errors import ApiError
from ..util import Json, body

log = logging.getLogger("fligel.api")


@dataclass
class Ctx:
    request: Request
    p: Principal | None
    data: dict = field(default_factory=dict)

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
        async def handler(request: Request) -> Response:
            try:
                p = None if public else principal(request, min_role)
                data = await body(request) if request.method in ("POST", "PUT", "PATCH") else {}
                result = await run_in_threadpool(fn, Ctx(request, p, data))
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
        return handler

    return wrap
