"""Задачи команды: поручить сотруднику, срок, повтор (раз в неделю / месяц), отметка «сделано» с телефона, просрочка."""
from starlette.routing import Route

from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_date, parse_uuid, req_str
from .base import Ctx, api

RECURRENCE = {"none": "Не повторять", "weekly": "Каждую неделю", "monthly": "Каждый месяц"}
SELECT = """SELECT t.id, t.title, t.description, t.property_id, t.room_id, t.booking_id, t.assignee_id, t.due_date,
    t.recurrence, t.source, t.done_at, t.created_at, u.name AS assignee_name, r.name AS room_name, p.name AS property_name,
    du.name AS done_by_name,
    (t.done_at IS NULL AND t.due_date IS NOT NULL AND t.due_date < current_date) AS overdue
  FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id LEFT JOIN rooms r ON r.id = t.room_id
  LEFT JOIN properties p ON p.id = t.property_id LEFT JOIN users du ON du.id = t.done_by"""


def create_task(conn, account_id, title: str, *, description: str = "", assignee_id=None, due_date=None, recurrence: str = "none",
                room_id=None, property_id=None, booking_id=None, source: str = "manual", created_by=None) -> dict:
    """Общая вставка: используется и API, и автопилотом, и (позже) складом, счётчиками, инвентаризацией."""
    if recurrence not in RECURRENCE:
        recurrence = "none"
    if room_id and not property_id:
        r = one(conn, "SELECT property_id FROM rooms WHERE id = %s AND account_id = %s", (room_id, account_id))
        property_id = r["property_id"] if r else None
    return one(conn, "INSERT INTO tasks (account_id, title, description, property_id, room_id, booking_id, assignee_id, due_date,"
                     " recurrence, source, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (account_id, title[:200], description[:2000], property_id, room_id, booking_id, assignee_id, due_date,
                recurrence, source, created_by))


def _fields(conn, c: Ctx, d: dict, current: dict | None = None) -> dict:
    out: dict = {}
    if current is None or "title" in d:
        out["title"] = req_str(d, "title", "Название задачи", 200)
    if current is None or "description" in d:
        out["description"] = opt_str(d, "description", max_len=2000)
    if current is None or "recurrence" in d:
        rec = d.get("recurrence") or "none"
        if rec not in RECURRENCE:
            raise ApiError(422, "Неверный повтор задачи")
        out["recurrence"] = rec
    if current is None or "due_date" in d:
        out["due_date"] = parse_date(d["due_date"], "Срок", "due_date") if d.get("due_date") else None
    if current is None or "assignee_id" in d:
        aid = d.get("assignee_id")
        if aid:
            aid = parse_uuid(aid, "Сотрудник")
            if not one(conn, "SELECT 1 FROM users WHERE id = %s AND account_id = %s AND role <> 'landlord'", (aid, c.account_id)):
                raise ApiError(404, "Сотрудник не найден")
        out["assignee_id"] = aid or None
    if current is None or "room_id" in d:
        rid = d.get("room_id")
        if rid:
            rid = parse_uuid(rid, "Номер")
            room = one(conn, "SELECT property_id FROM rooms WHERE id = %s AND account_id = %s", (rid, c.account_id))
            if not room:
                raise ApiError(404, "Номер не найден")
            out["property_id"] = room["property_id"]
        else:
            out["property_id"] = None
        out["room_id"] = rid or None
    if out.get("recurrence", "none") != "none" and current is None and not out.get("due_date"):
        raise ApiError(422, "Для повторяющейся задачи укажите срок — от него считается следующая", {"field": "due_date"})
    return out


@api()
def list_tasks(c: Ctx):
    """Горничная видит свои задачи и задачи «на всех»; администратор и владелец — все."""
    scope = c.q.get("scope") or "open"
    where, params = ["t.account_id = %s"], [c.account_id]
    staff_view = c.p.role in ("owner", "manager")
    if not staff_view:
        where.append("(t.assignee_id = %s OR t.assignee_id IS NULL)")
        params.append(c.p.user_id)
    elif c.q.get("assignee") == "me":
        where.append("t.assignee_id = %s")
        params.append(c.p.user_id)
    elif c.q.get("assignee"):
        where.append("t.assignee_id = %s")
        params.append(parse_uuid(c.q.get("assignee"), "Сотрудник"))
    if scope == "done":
        where.append("t.done_at IS NOT NULL AND t.done_at > now() - interval '30 days'")
        order = "t.done_at DESC"
    elif scope == "overdue":
        where.append("t.done_at IS NULL AND t.due_date < current_date")
        order = "t.due_date, t.created_at"
    else:
        where.append("t.done_at IS NULL")
        order = "t.due_date NULLS LAST, t.created_at"
    with tx() as conn:
        items = all_(conn, f"{SELECT} WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 300", params)
        counts = one(conn, "SELECT count(*) FILTER (WHERE done_at IS NULL) AS open,"
                           " count(*) FILTER (WHERE done_at IS NULL AND due_date < current_date) AS overdue,"
                           " count(*) FILTER (WHERE done_at IS NULL AND due_date = current_date) AS today"
                           " FROM tasks WHERE account_id = %s" + ("" if staff_view else " AND (assignee_id = %s OR assignee_id IS NULL)"),
                     (c.account_id,) if staff_view else (c.account_id, c.p.user_id))
        staff = all_(conn, "SELECT id, name, role FROM users WHERE account_id = %s ORDER BY name", (c.account_id,)) if staff_view else []
        rooms = all_(conn, "SELECT r.id, r.name, p.name AS property_name FROM rooms r JOIN properties p ON p.id = r.property_id"
                           " WHERE r.account_id = %s ORDER BY p.created_at, r.sort_order, r.name", (c.account_id,)) if staff_view else []
    return {"items": items, "counts": counts, "staff": staff, "rooms": rooms, "recurrence": RECURRENCE, "me": c.p.user_id}


@api("manager")
def create(c: Ctx):
    with tx() as conn:
        f = _fields(conn, c, c.data)
        row = create_task(conn, c.account_id, f["title"], description=f["description"], assignee_id=f["assignee_id"],
                          due_date=f["due_date"], recurrence=f["recurrence"], room_id=f["room_id"], created_by=c.p.user_id)
        return one(conn, f"{SELECT} WHERE t.id = %s", (row["id"],))


def _own(conn, c: Ctx, tid) -> dict:
    t = one(conn, "SELECT * FROM tasks WHERE id = %s AND account_id = %s FOR UPDATE", (parse_uuid(tid, "Задача"), c.account_id))
    if not t:
        raise ApiError(404, "Задача не найдена")
    return t


@api("manager")
def update(c: Ctx):
    with tx() as conn:
        t = _own(conn, c, c.path["id"])
        f = _fields(conn, c, c.data, t)
        if f:
            sets = ", ".join(f"{k} = %s" for k in f)
            run(conn, f"UPDATE tasks SET {sets} WHERE id = %s", (*f.values(), t["id"]))
        return one(conn, f"{SELECT} WHERE t.id = %s", (t["id"],))


@api()
def done(c: Ctx):
    """Отметить сделанной (или вернуть: {"undo": true}). Горничная может закрыть только свою или «общую» задачу.
    У повторяющейся задачи сразу появляется следующая (срок +неделя / +месяц от прежнего срока)."""
    undo = bool(c.data.get("undo"))
    with tx() as conn:
        t = _own(conn, c, c.path["id"])
        if c.p.role not in ("owner", "manager") and (t["assignee_id"] is not None and str(t["assignee_id"]) != str(c.p.user_id)):
            raise ApiError(403, "Эта задача поручена другому сотруднику")
        if undo:
            run(conn, "UPDATE tasks SET done_at = NULL, done_by = NULL WHERE id = %s", (t["id"],))
        elif not t["done_at"]:
            run(conn, "UPDATE tasks SET done_at = now(), done_by = %s, recurrence = 'none' WHERE id = %s", (c.p.user_id, t["id"]))
            if t["recurrence"] != "none":
                step = "interval '7 days'" if t["recurrence"] == "weekly" else "interval '1 month'"
                base = t["due_date"] or one(conn, "SELECT current_date AS d")["d"]
                nxt = one(conn, f"SELECT (%s::date + {step})::date AS d", (base,))["d"]
                while nxt < one(conn, "SELECT current_date AS d")["d"]:  # просроченную повторяющуюся не копим в прошлом
                    nxt = one(conn, f"SELECT (%s::date + {step})::date AS d", (nxt,))["d"]
                create_task(conn, c.account_id, t["title"], description=t["description"], assignee_id=t["assignee_id"],
                            due_date=nxt, recurrence=t["recurrence"], room_id=t["room_id"], property_id=t["property_id"],
                            source=t["source"], created_by=t["created_by"])
        return one(conn, f"{SELECT} WHERE t.id = %s", (t["id"],))


@api("manager")
def delete(c: Ctx):
    with tx() as conn:
        if not run(conn, "DELETE FROM tasks WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Задача"), c.account_id)):
            raise ApiError(404, "Задача не найдена")
    return {"ok": True}


def overdue_count(conn, account_id, user_id, staff: bool) -> int:
    """Для значка в меню: просроченные задачи (свои и «общие»; у владельца/администратора — все)."""
    if staff:
        return one(conn, "SELECT count(*) AS n FROM tasks WHERE account_id = %s AND done_at IS NULL AND due_date < current_date",
                   (account_id,))["n"]
    return one(conn, "SELECT count(*) AS n FROM tasks WHERE account_id = %s AND done_at IS NULL AND due_date < current_date"
                     " AND (assignee_id = %s OR assignee_id IS NULL)", (account_id, user_id))["n"]


routes = [
    Route("/api/tasks", list_tasks),
    Route("/api/tasks", create, methods=["POST"]),
    Route("/api/tasks/{id}", update, methods=["PATCH"]),
    Route("/api/tasks/{id}", delete, methods=["DELETE"]),
    Route("/api/tasks/{id}/done", done, methods=["POST"]),
]
