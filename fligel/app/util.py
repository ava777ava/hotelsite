"""Разбор входных данных запросов и сериализация ответов."""
import json
import re
import uuid
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from .errors import ApiError


def _default(o: Any):
    if isinstance(o, (date, datetime, time)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, uuid.UUID):
        return str(o)
    raise TypeError(f"Не сериализуется: {type(o)}")


class Json(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(content, ensure_ascii=False, default=_default).encode("utf-8")


async def body(request: Request) -> dict:
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        raise ApiError(400, "Ожидался JSON в теле запроса")
    if not isinstance(data, dict):
        raise ApiError(400, "Ожидался JSON-объект")
    return data


def req_str(data: dict, key: str, label: str, max_len: int = 500) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise ApiError(422, f"Заполните поле «{label}»", {"field": key})
    return value[:max_len]


def opt_str(data: dict, key: str, default: str = "", max_len: int = 2000) -> str:
    value = data.get(key)
    return default if value is None else str(value).strip()[:max_len]


def parse_date(value: Any, label: str = "Дата", field: str | None = None) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        raise ApiError(422, f"{label}: нужна дата в формате ГГГГ-ММ-ДД", {"field": field} if field else None)


def parse_uuid(value: Any, label: str = "Идентификатор") -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        raise ApiError(422, f"{label}: неверный формат")


def parse_money(value: Any, label: str = "Сумма") -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        d = Decimal(str(value).replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        raise ApiError(422, f"{label}: нужно число")
    if d < 0:
        raise ApiError(422, f"{label} не может быть отрицательной")
    return d.quantize(Decimal("0.01"))


def parse_int(value: Any, label: str, minimum: int = 0, default: int | None = None) -> int:
    if value in (None, "") and default is not None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ApiError(422, f"{label}: нужно целое число")
    if n < minimum:
        raise ApiError(422, f"{label}: минимум {minimum}")
    return n


def slugify(text: str) -> str:
    table = str.maketrans({
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
        "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    })
    s = text.lower().translate(table)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40] or "object"
