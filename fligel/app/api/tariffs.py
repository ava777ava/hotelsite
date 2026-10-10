"""Тарифы категории номеров: невозвратный, с завтраком и т. п. (± % и ± ₽ к цене ночи)."""
from decimal import Decimal, InvalidOperation

from starlette.routing import Route

from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import req_str, parse_uuid
from .base import Ctx, api

COLS = "id, room_type_id, name, description, percent_delta, fixed_delta, refundable, breakfast, active, sort_order"


def _num(v, label: str, lo: float, hi: float) -> Decimal:
    try:
        d = Decimal(str(v if v not in (None, "") else 0).replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        raise ApiError(422, f"{label}: нужно число")
    if d < Decimal(str(lo)) or d > Decimal(str(hi)):
        raise ApiError(422, f"{label}: допустимо от {lo:g} до {hi:g}")
    return d.quantize(Decimal("0.01"))


def get_plan(conn, account_id, plan_id, room_type_id=None) -> dict | None:
    """Тариф для расчёта цены: должен принадлежать аккаунту (и категории, если она известна)."""
    if not plan_id:
        return None
    p = one(conn, f"SELECT {COLS} FROM rate_plans WHERE id = %s AND account_id = %s",
            (parse_uuid(plan_id, "Тариф"), account_id))
    if not p:
        raise ApiError(404, "Тариф не найден")
    if room_type_id and str(p["room_type_id"]) != str(room_type_id):
        raise ApiError(422, "Этот тариф относится к другой категории номеров")
    return p


@api("manager")
def list_plans(c: Ctx):
    with tx() as conn:
        rt = parse_uuid(c.path["id"], "Категория")
        if not one(conn, "SELECT 1 FROM room_types WHERE id = %s AND account_id = %s", (rt, c.account_id)):
            raise ApiError(404, "Категория не найдена")
        return all_(conn, f"SELECT {COLS} FROM rate_plans WHERE room_type_id = %s AND account_id = %s"
                          " ORDER BY sort_order, created_at", (rt, c.account_id))


def _values(d: dict, old: dict | None = None) -> dict:
    v = dict(old or {"name": "", "description": "", "percent_delta": Decimal(0), "fixed_delta": Decimal(0),
                     "refundable": True, "breakfast": False, "active": True})
    if "name" in d or not old:
        v["name"] = req_str(d, "name", "Название тарифа", 100)
    if "description" in d:
        v["description"] = str(d["description"] or "")[:500]
    if "percent_delta" in d:
        v["percent_delta"] = _num(d["percent_delta"], "Изменение цены, %", -90, 300)
    if "fixed_delta" in d:
        v["fixed_delta"] = _num(d["fixed_delta"], "Изменение цены, ₽ за ночь", -1_000_000, 1_000_000)
    for k in ("refundable", "breakfast", "active"):
        if k in d:
            v[k] = bool(d[k])
    return v


@api("owner")
def create_plan(c: Ctx):
    rt = parse_uuid(c.path["id"], "Категория")
    v = _values(c.data)
    with tx() as conn:
        if not one(conn, "SELECT 1 FROM room_types WHERE id = %s AND account_id = %s", (rt, c.account_id)):
            raise ApiError(404, "Категория не найдена")
        if one(conn, "SELECT count(*) AS n FROM rate_plans WHERE room_type_id = %s", (rt,))["n"] >= 10:
            raise ApiError(422, "У категории может быть не больше 10 тарифов")
        return one(conn, "INSERT INTO rate_plans (account_id, room_type_id, name, description, percent_delta, fixed_delta,"
                         " refundable, breakfast, active, sort_order) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
                         " (SELECT coalesce(max(sort_order), 0) + 1 FROM rate_plans WHERE room_type_id = %s))"
                         f" RETURNING {COLS}",
                   (c.account_id, rt, v["name"], v["description"], v["percent_delta"], v["fixed_delta"],
                    v["refundable"], v["breakfast"], v["active"], rt))


@api("owner")
def update_plan(c: Ctx):
    pid = parse_uuid(c.path["id"], "Тариф")
    with tx() as conn:
        old = get_plan(conn, c.account_id, pid)
        v = _values(c.data, old)
        return one(conn, "UPDATE rate_plans SET name=%s, description=%s, percent_delta=%s, fixed_delta=%s,"
                         f" refundable=%s, breakfast=%s, active=%s WHERE id = %s RETURNING {COLS}",
                   (v["name"], v["description"], v["percent_delta"], v["fixed_delta"], v["refundable"],
                    v["breakfast"], v["active"], pid))


@api("owner")
def delete_plan(c: Ctx):
    with tx() as conn:
        if not run(conn, "DELETE FROM rate_plans WHERE id = %s AND account_id = %s",
                   (parse_uuid(c.path["id"], "Тариф"), c.account_id)):
            raise ApiError(404, "Тариф не найден")
    return {"ok": True}


routes = [
    Route("/api/room-types/{id}/plans", list_plans),
    Route("/api/room-types/{id}/plans", create_plan, methods=["POST"]),
    Route("/api/plans/{id}", update_plan, methods=["PATCH"]),
    Route("/api/plans/{id}", delete_plan, methods=["DELETE"]),
]
