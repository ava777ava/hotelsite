"""Автоцены: настройка правил и режима (выключено / предлагать / применять самому), список предложений, журнал изменений."""
from decimal import Decimal

from starlette.routing import Route

from .. import audit, autoprice
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import parse_int, parse_money, parse_uuid
from .base import Ctx, api

MODES = {"off": "Выключены", "suggest": "Только предлагать (цены меняете вы)", "auto": "Менять цены самим (с журналом)"}
MAX_RULES = 50


def _rule_fields(conn, c: Ctx, d: dict, cur: dict | None) -> dict:
    out: dict = {}
    if cur is None or "kind" in d:
        if d.get("kind") not in autoprice.KINDS:
            raise ApiError(422, "Выберите тип правила")
        out["kind"] = d["kind"]
    kind = out.get("kind") or cur["kind"]
    if cur is None or "percent" in d:
        try:
            pct = Decimal(str(d.get("percent")).replace(",", ".").replace(" ", ""))
        except Exception:  # noqa: BLE001
            raise ApiError(422, "Процент: нужно число", {"field": "percent"})
        if not pct.is_finite() or pct == 0 or pct < -90 or pct > 300:
            raise ApiError(422, "Процент: от −90 до +300, не ноль", {"field": "percent"})
        if kind == "low_occupancy" and pct > 0:
            raise ApiError(422, "При низкой загрузке цену можно только снижать", {"field": "percent"})
        if kind in ("weekend", "holiday", "last_room") and pct < 0:
            raise ApiError(422, "Для этого правила цену можно только повышать", {"field": "percent"})
        out["percent"] = pct.quantize(Decimal("0.1"))
    if cur is None or "days_ahead" in d:
        out["days_ahead"] = min(parse_int(d.get("days_ahead"), "Дней вперёд", 0, default=14), 180)
    if cur is None or "threshold" in d:
        th = parse_int(d.get("threshold"), "Порог загрузки", 1, default=40)
        if th > 100:
            raise ApiError(422, "Порог загрузки: от 1 до 100 %", {"field": "threshold"})
        out["threshold"] = th
    if cur is None or "room_type_id" in d:
        rid = d.get("room_type_id")
        if rid:
            rid = parse_uuid(rid, "Категория")
            if not one(conn, "SELECT 1 FROM room_types WHERE id = %s AND account_id = %s", (rid, c.account_id)):
                raise ApiError(404, "Категория не найдена")
        out["room_type_id"] = rid or None
    if "enabled" in d or cur is None:
        out["enabled"] = bool(d.get("enabled", True))
    return out


@api("manager")
def overview(c: Ctx):
    with tx() as conn:
        st = one(conn, "SELECT mode, horizon_days, last_run_on FROM price_settings WHERE account_id = %s", (c.account_id,)) \
            or {"mode": "off", "horizon_days": 60, "last_run_on": None}
        rules = all_(conn, "SELECT * FROM price_rules WHERE account_id = %s ORDER BY created_at", (c.account_id,))
        types = all_(conn, "SELECT rt.id, rt.name, rt.base_price, rt.min_price, rt.max_price, p.name AS property_name FROM room_types rt"
                           " JOIN properties p ON p.id = rt.property_id WHERE rt.account_id = %s ORDER BY p.created_at, rt.sort_order, rt.name", (c.account_id,))
        suggestions = all_(conn, "SELECT s.id, s.date, s.current_price, s.suggested_price, s.reasons, rt.name AS type_name FROM price_suggestions s"
                                 " JOIN room_types rt ON rt.id = s.room_type_id WHERE s.account_id = %s AND s.status = 'pending'"
                                 " ORDER BY s.date, rt.name LIMIT %s", (c.account_id, autoprice.PREVIEW_LIMIT))
        changes = all_(conn, "SELECT x.id, x.date, x.old_price, x.new_price, x.reasons, x.source, x.created_at, rt.name AS type_name, u.name AS user_name"
                             " FROM price_changes x JOIN room_types rt ON rt.id = x.room_type_id LEFT JOIN users u ON u.id = x.user_id"
                             " WHERE x.account_id = %s ORDER BY x.created_at DESC, x.date LIMIT 100", (c.account_id,))
    return {"settings": st, "modes": MODES, "kinds": autoprice.KINDS, "rules": rules, "types": types, "suggestions": suggestions, "changes": changes,
            "can_edit": c.p.role == "owner",
            "note": "Праздники — только даты с фиксированным числом (Новый год, 23 февраля, 8 марта, 1 и 9 мая, 12 июня, 4 ноября); "
                    "переносы выходных задайте вручную в календаре цен. Если цена на дату поставлена вручную, проценты считаются от неё."}


@api("owner")
def save_settings(c: Ctx):
    mode = c.data.get("mode")
    if mode not in MODES:
        raise ApiError(422, "Неверный режим")
    horizon = min(max(parse_int(c.data.get("horizon_days"), "Горизонт (дней)", 7, default=60), 7), 180)
    with tx() as conn:
        run(conn, "INSERT INTO price_settings (account_id, mode, horizon_days) VALUES (%s, %s, %s)"
                  " ON CONFLICT (account_id) DO UPDATE SET mode = EXCLUDED.mode, horizon_days = EXCLUDED.horizon_days, updated_at = now()",
            (c.account_id, mode, horizon))
        audit.record(conn, c.account_id, c.p.user_id, "autoprice_mode", f"Автоцены: режим «{MODES[mode]}»")
        result = autoprice.refresh(conn, c.account_id) if mode != "off" else {"mode": "off", "proposed": 0, "applied": 0}
        if mode == "off":
            run(conn, "DELETE FROM price_suggestions WHERE account_id = %s AND status = 'pending'", (c.account_id,))
    return result


@api("owner")
def create_rule(c: Ctx):
    with tx() as conn:
        if one(conn, "SELECT count(*) AS n FROM price_rules WHERE account_id = %s", (c.account_id,))["n"] >= MAX_RULES:
            raise ApiError(422, f"Слишком много правил (максимум {MAX_RULES})")
        f = _rule_fields(conn, c, c.data, None)
        row = one(conn, f"INSERT INTO price_rules (account_id, {', '.join(f)}) VALUES (%s, {', '.join(['%s'] * len(f))}) RETURNING *", (c.account_id, *f.values()))
        audit.record(conn, c.account_id, c.p.user_id, "autoprice_rule", f"Правило автоцен: {autoprice.KINDS[f['kind']]}, {f['percent']} %")
        return row


@api("owner")
def update_rule(c: Ctx):
    rid = parse_uuid(c.path["id"], "Правило")
    with tx() as conn:
        cur = one(conn, "SELECT * FROM price_rules WHERE id = %s AND account_id = %s FOR UPDATE", (rid, c.account_id))
        if not cur:
            raise ApiError(404, "Правило не найдено")
        f = _rule_fields(conn, c, c.data, cur)
        if f:
            run(conn, f"UPDATE price_rules SET {', '.join(f'{k} = %s' for k in f)} WHERE id = %s", (*f.values(), rid))
        return one(conn, "SELECT * FROM price_rules WHERE id = %s", (rid,))


@api("owner")
def delete_rule(c: Ctx):
    with tx() as conn:
        if not run(conn, "DELETE FROM price_rules WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Правило"), c.account_id)):
            raise ApiError(404, "Правило не найдено")
    return {"ok": True}


@api("owner")
def refresh_now(c: Ctx):
    with tx() as conn:
        return autoprice.refresh(conn, c.account_id)


@api("owner")
def preview(c: Ctx):
    """Что изменили бы правила прямо сейчас — без записи (для режима «выключено» и проверки правил)."""
    with tx() as conn:
        items = autoprice.compute(conn, c.account_id)
    return {"items": items[:autoprice.PREVIEW_LIMIT], "total": len(items)}


def _decide(c: Ctx, apply: bool) -> dict:
    ids = c.data.get("ids")
    with tx() as conn:
        if ids == "all":
            rows = all_(conn, "SELECT * FROM price_suggestions WHERE account_id = %s AND status = 'pending' FOR UPDATE", (c.account_id,))
        else:
            if not isinstance(ids, list) or not ids:
                raise ApiError(422, "Выберите предложения")
            rows = all_(conn, "SELECT * FROM price_suggestions WHERE account_id = %s AND status = 'pending' AND id = ANY(%s::uuid[]) FOR UPDATE",
                        (c.account_id, [parse_uuid(i, "Предложение") for i in ids[:2000]]))
        for s in rows:
            if apply:
                autoprice._apply_one(conn, c.account_id, {"room_type_id": s["room_type_id"], "date": s["date"],
                                                          "suggested_price": s["suggested_price"], "base_price": s["base_price"], "reasons": s["reasons"]}, "suggestion", c.p.user_id)
            run(conn, "UPDATE price_suggestions SET status = %s, decided_at = now(), decided_by = %s WHERE id = %s",
                ("applied" if apply else "dismissed", c.p.user_id, s["id"]))
        if rows and apply:
            audit.record(conn, c.account_id, c.p.user_id, "autoprice_applied", f"Применены предложенные цены: {len(rows)}")
    return {"count": len(rows)}


@api("owner")
def apply_suggestions(c: Ctx):
    return _decide(c, True)


@api("owner")
def dismiss_suggestions(c: Ctx):
    return _decide(c, False)


routes = [
    Route("/api/autoprice", overview),
    Route("/api/autoprice/settings", save_settings, methods=["PUT"]),
    Route("/api/autoprice/rules", create_rule, methods=["POST"]),
    Route("/api/autoprice/rules/{id}", update_rule, methods=["PATCH"]),
    Route("/api/autoprice/rules/{id}", delete_rule, methods=["DELETE"]),
    Route("/api/autoprice/refresh", refresh_now, methods=["POST"]),
    Route("/api/autoprice/preview", preview),
    Route("/api/autoprice/apply", apply_suggestions, methods=["POST"]),
    Route("/api/autoprice/dismiss", dismiss_suggestions, methods=["POST"]),
]
