"""Автопилот: настройка сценариев «событие → условие → действие» и журнал срабатываний (только владелец)."""
import json

from starlette.routing import Route

from .. import audit, automation
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_int, parse_uuid, req_str
from .base import Ctx, api
from .bookings import SOURCES
from .guests import PLACEHOLDERS

RULE_SQL = """SELECT r.id, r.preset, r.name, r.event, r.offset_days, r.at_hour, r.only_unpaid, r.sources, r.property_id, r.action,
    r.params, r.enabled, r.created_at,
    (SELECT count(*) FROM automation_runs x WHERE x.rule_id = r.id) AS runs,
    (SELECT count(*) FROM automation_runs x WHERE x.rule_id = r.id AND x.status = 'error') AS errors,
    (SELECT max(x.created_at) FROM automation_runs x WHERE x.rule_id = r.id) AS last_run_at
  FROM automation_rules r"""
HINTS = {p["key"]: p["hint"] for p in automation.PRESETS}


def _clean_params(conn, c: Ctx, action: str, raw: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    if action == "notify_staff":
        return {"text": req_str(raw, "text", "Текст сообщения", 1000)}
    if action == "email_guest":
        return {"subject": req_str(raw, "subject", "Тема письма", 200), "body": req_str(raw, "body", "Текст письма", 3000),
                "notify_if_missing": raw.get("notify_if_missing", True) is not False}
    if action == "create_task":
        aid = raw.get("assignee_id")
        if aid:
            aid = parse_uuid(aid, "Сотрудник")
            if not one(conn, "SELECT 1 FROM users WHERE id = %s AND account_id = %s AND role <> 'landlord'", (aid, c.account_id)):
                raise ApiError(404, "Сотрудник не найден")
        return {"title": req_str(raw, "title", "Название задачи", 200), "description": opt_str(raw, "description", max_len=1000),
                "due_in_days": min(parse_int(raw.get("due_in_days"), "Срок задачи (дней)", 0, default=0), 60),
                "assignee_id": aid or None, "notify": raw.get("notify", True) is not False}
    if action == "set_cleaning":
        return {"status": raw.get("status") if raw.get("status") in ("dirty", "inspect") else "dirty", "notify": raw.get("notify", True) is not False}
    raise ApiError(422, "Неизвестное действие")


def _fields(conn, c: Ctx, d: dict, current: dict | None) -> dict:
    out: dict = {}
    preset = current is not None and current["preset"]
    if current is None or ("name" in d and not preset):
        out["name"] = req_str(d, "name", "Название сценария", 120)
    event = current["event"] if (preset or (current and "event" not in d)) else d.get("event")
    if current is None or ("event" in d and not preset):
        if event not in automation.EVENTS:
            raise ApiError(422, "Выберите событие")
        out["event"] = event
    action = current["action"] if (preset or (current and "action" not in d)) else d.get("action")
    if current is None or ("action" in d and not preset):
        if action not in automation.ACTIONS:
            raise ApiError(422, "Выберите действие")
        out["action"] = action
    if current is None or "offset_days" in d:
        out["offset_days"] = min(parse_int(d.get("offset_days"), "Число дней", 0, default=0), 60)
    if current is None or "at_hour" in d:
        h = parse_int(d.get("at_hour"), "Час", 0, default=10)
        if h > 23:
            raise ApiError(422, "Час: от 0 до 23")
        out["at_hour"] = h
    if current is None or "only_unpaid" in d:
        out["only_unpaid"] = bool(d.get("only_unpaid"))
    if current is None or "sources" in d:
        src = d.get("sources") or []
        if not isinstance(src, list) or any(s not in SOURCES for s in src):
            raise ApiError(422, "Неверный источник брони")
        out["sources"] = list(dict.fromkeys(src))
    if current is None or "property_id" in d:
        pid = d.get("property_id")
        if pid:
            pid = parse_uuid(pid, "Объект")
            if not one(conn, "SELECT 1 FROM properties WHERE id = %s AND account_id = %s", (pid, c.account_id)):
                raise ApiError(404, "Объект не найден")
        out["property_id"] = pid or None
    if current is None or "params" in d:
        out["params"] = json.dumps(_clean_params(conn, c, action, d.get("params")), ensure_ascii=False)
    if "enabled" in d or current is None:
        out["enabled"] = bool(d.get("enabled", True))
    return out


@api("owner")
def overview(c: Ctx):
    with tx() as conn:
        # старые аккаунты получают готовые сценарии выключенными — ничего не начнёт отправляться без их ведома
        automation.ensure_presets(conn, c.account_id, use_defaults=False)
        rules = all_(conn, f"{RULE_SQL} WHERE r.account_id = %s ORDER BY (r.preset IS NULL), r.created_at, r.name", (c.account_id,))
        staff = all_(conn, "SELECT id, name, role FROM users WHERE account_id = %s AND role <> 'landlord' ORDER BY name", (c.account_id,))
        props = all_(conn, "SELECT id, name FROM properties WHERE account_id = %s ORDER BY created_at", (c.account_id,))
    order = [p["key"] for p in automation.PRESETS]
    rules.sort(key=lambda r: (r["preset"] is None, order.index(r["preset"]) if r["preset"] in order else 0, r["created_at"]))
    for r in rules:
        r["hint"] = HINTS.get(r["preset"], "")
    return {"rules": rules, "events": automation.EVENTS, "actions": automation.ACTIONS, "placeholders": PLACEHOLDERS,
            "staff": staff, "properties": props, "sources": list(SOURCES)}


@api("owner")
def create(c: Ctx):
    with tx() as conn:
        f = _fields(conn, c, c.data, None)
        row = one(conn, f"INSERT INTO automation_rules (account_id, {', '.join(f)}) VALUES (%s, {', '.join(['%s'] * len(f))}) RETURNING id",
                  (c.account_id, *f.values()))
        audit.record(conn, c.account_id, c.p.user_id, "automation_created", f"Новый сценарий автопилота: «{f['name']}»", "automation_rule", row["id"])
        return one(conn, f"{RULE_SQL} WHERE r.id = %s", (row["id"],))


@api("owner")
def update(c: Ctx):
    rid = parse_uuid(c.path["id"], "Сценарий")
    with tx() as conn:
        cur = one(conn, "SELECT * FROM automation_rules WHERE id = %s AND account_id = %s FOR UPDATE", (rid, c.account_id))
        if not cur:
            raise ApiError(404, "Сценарий не найден")
        f = _fields(conn, c, c.data, cur)
        if f:
            run(conn, f"UPDATE automation_rules SET {', '.join(f'{k} = %s' for k in f)} WHERE id = %s", (*f.values(), rid))
            if "enabled" in f and f["enabled"] != cur["enabled"]:
                audit.record(conn, c.account_id, c.p.user_id, "automation_toggled",
                             f"Сценарий автопилота «{cur['name']}» {'включён' if f['enabled'] else 'выключен'}", "automation_rule", rid)
        row = one(conn, f"{RULE_SQL} WHERE r.id = %s", (rid,))
        row["hint"] = HINTS.get(row["preset"], "")
        return row


@api("owner")
def delete(c: Ctx):
    rid = parse_uuid(c.path["id"], "Сценарий")
    with tx() as conn:
        cur = one(conn, "SELECT preset, name FROM automation_rules WHERE id = %s AND account_id = %s", (rid, c.account_id))
        if not cur:
            raise ApiError(404, "Сценарий не найден")
        if cur["preset"]:
            raise ApiError(422, "Готовый сценарий нельзя удалить — выключите его переключателем")
        run(conn, "DELETE FROM automation_rules WHERE id = %s", (rid,))
        audit.record(conn, c.account_id, c.p.user_id, "automation_deleted", f"Сценарий автопилота «{cur['name']}» удалён", "automation_rule", rid)
    return {"ok": True}


@api("owner")
def runs(c: Ctx):
    with tx() as conn:
        items = all_(conn, "SELECT x.id, x.status, x.detail, x.created_at, r.name AS rule_name, b.id AS booking_id, b.guest_name,"
                           " b.check_in, b.check_out, rm.name AS room_name"
                           " FROM automation_runs x JOIN automation_rules r ON r.id = x.rule_id JOIN bookings b ON b.id = x.booking_id"
                           " JOIN rooms rm ON rm.id = b.room_id WHERE x.account_id = %s ORDER BY x.created_at DESC LIMIT 100", (c.account_id,))
    return {"items": items}


@api("owner")
def run_now(c: Ctx):
    """«Проверить сейчас»: тот же проход, что делает планировщик раз в полминуты, только по требованию (по этому аккаунту)."""
    with tx() as conn:
        rules = all_(conn, "SELECT * FROM automation_rules WHERE account_id = %s AND enabled", (c.account_id,))
    return {"fired": sum(automation.run_rule(r) for r in rules)}


routes = [
    Route("/api/automation", overview),
    Route("/api/automation/rules", create, methods=["POST"]),
    Route("/api/automation/rules/{id}", update, methods=["PATCH"]),
    Route("/api/automation/rules/{id}", delete, methods=["DELETE"]),
    Route("/api/automation/runs", runs),
    Route("/api/automation/run", run_now, methods=["POST"]),
]
