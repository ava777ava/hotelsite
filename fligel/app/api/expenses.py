"""Расходы: категории, сами расходы, повторяющиеся шаблоны, выгрузка в CSV.

Права: смотреть — администратор и владелец (как остальные финансовые разделы);
добавлять и редактировать расход — администратор и владелец; удалять расход и
управлять категориями/шаблонами — только владелец.
"""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from starlette.responses import Response
from starlette.routing import Route

from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_date, parse_int, parse_money, parse_uuid, req_str
from .base import Ctx, api

EXPENSE_COLS_PLAIN = "id, property_id, room_id, category_id, date, amount, comment, recurring_rule_id, created_at"
EXPENSE_COLS = ("e.id, e.property_id, e.room_id, e.category_id, e.date, e.amount, e.comment,"
                " e.recurring_rule_id, e.created_at")


def _date_range(c: Ctx) -> tuple[date, date]:
    if c.q.get("from"):
        start = parse_date(c.q["from"], "Начало периода")
    else:
        today = date.today()
        start = today.replace(day=1)
    end = parse_date(c.q["to"], "Конец периода") if c.q.get("to") else date.today() + timedelta(days=1)
    if end <= start:
        raise ApiError(422, "Конец периода должен быть позже начала")
    return start, end


def _category(conn, account_id: str, category_id) -> dict:
    cat = one(conn, "SELECT * FROM expense_categories WHERE id = %s AND account_id = %s",
              (parse_uuid(category_id, "Категория"), account_id))
    if not cat:
        raise ApiError(404, "Категория не найдена")
    return cat


# ---------- категории ----------

@api("manager")
def list_categories(c: Ctx):
    with tx() as conn:
        where = "account_id = %s" if c.q.get("include_archived") == "1" else "account_id = %s AND NOT archived"
        return all_(conn, f"SELECT * FROM expense_categories WHERE {where} ORDER BY sort_order, name",
                   (c.account_id,))


@api("owner")
def create_category(c: Ctx):
    name = req_str(c.data, "name", "Название категории", 100)
    color = opt_str(c.data, "color", "#69755F", 20) or "#69755F"
    with tx() as conn:
        if one(conn, "SELECT 1 FROM expense_categories WHERE account_id = %s AND lower(name) = lower(%s)"
                     " AND NOT archived", (c.account_id, name)):
            raise ApiError(409, "Категория с таким названием уже есть")
        order = one(conn, "SELECT coalesce(max(sort_order), -1) + 1 AS n FROM expense_categories"
                          " WHERE account_id = %s", (c.account_id,))["n"]
        return one(conn, "INSERT INTO expense_categories (account_id, name, color, sort_order)"
                         " VALUES (%s, %s, %s, %s) RETURNING *", (c.account_id, name, color, order))


@api("owner")
def update_category(c: Ctx):
    cat_id = parse_uuid(c.path["id"])
    d = c.data
    sets, params = [], []
    new_name = None
    if "name" in d:
        new_name = req_str(d, "name", "Название", 100)
        sets.append("name = %s"); params.append(new_name)
    if "color" in d:
        sets.append("color = %s"); params.append(opt_str(d, "color", "#69755F", 20) or "#69755F")
    if "archived" in d:
        sets.append("archived = %s"); params.append(bool(d["archived"]))
    if "sort_order" in d:
        sets.append("sort_order = %s"); params.append(parse_int(d["sort_order"], "Порядок", 0))
    if not sets:
        raise ApiError(422, "Нечего сохранять")
    with tx() as conn:
        if new_name and one(conn, "SELECT 1 FROM expense_categories WHERE account_id = %s AND lower(name) = lower(%s)"
                                  " AND NOT archived AND id <> %s", (c.account_id, new_name, cat_id)):
            raise ApiError(409, "Категория с таким названием уже есть")
        row = one(conn, f"UPDATE expense_categories SET {', '.join(sets)} WHERE id = %s AND account_id = %s"
                        " RETURNING *", (*params, cat_id, c.account_id))
    if not row:
        raise ApiError(404, "Категория не найдена")
    return row


# ---------- расходы ----------

def _serialize_filters(c: Ctx):
    start, end = _date_range(c)
    where = ["e.account_id = %s"]
    params: list = [c.account_id]
    if c.q.get("property_id") == "none":
        where.append("e.property_id IS NULL")
    elif c.q.get("property_id"):
        where.append("e.property_id = %s")
        params.append(parse_uuid(c.q["property_id"], "Объект"))
    if c.q.get("category_id"):
        where.append("e.category_id = %s")
        params.append(parse_uuid(c.q["category_id"], "Категория"))
    where.append("e.date >= %s AND e.date < %s")
    params += [start, end]
    return start, end, where, params


@api("manager")
def list_expenses(c: Ctx):
    start, end, where, params = _serialize_filters(c)
    with tx() as conn:
        rows = all_(
            conn,
            f"SELECT {EXPENSE_COLS}, cat.name AS category_name, cat.color AS category_color,"
            " p.name AS property_name, r.name AS room_name, u.name AS created_by_name"
            " FROM expenses e JOIN expense_categories cat ON cat.id = e.category_id"
            " LEFT JOIN properties p ON p.id = e.property_id LEFT JOIN rooms r ON r.id = e.room_id"
            " LEFT JOIN users u ON u.id = e.created_by"
            f" WHERE {' AND '.join(where)} ORDER BY e.date DESC, e.created_at DESC LIMIT 2000",
            params,
        )
    total = sum((Decimal(r["amount"]) for r in rows), Decimal("0"))
    by_cat: dict[str, dict] = {}
    for r in rows:
        cid = str(r["category_id"])
        s = by_cat.setdefault(cid, {"category_id": r["category_id"], "category_name": r["category_name"],
                                    "category_color": r["category_color"], "amount": Decimal("0"), "count": 0})
        s["amount"] += Decimal(r["amount"])
        s["count"] += 1
    return {"from": start, "to": end, "rows": rows, "total": total,
            "by_category": sorted(by_cat.values(), key=lambda s: -s["amount"])}


@api("manager")
def export_expenses(c: Ctx):
    start, end, where, params = _serialize_filters(c)
    with tx() as conn:
        rows = all_(
            conn,
            f"SELECT {EXPENSE_COLS}, cat.name AS category_name, p.name AS property_name, r.name AS room_name,"
            " u.name AS created_by_name FROM expenses e JOIN expense_categories cat ON cat.id = e.category_id"
            " LEFT JOIN properties p ON p.id = e.property_id LEFT JOIN rooms r ON r.id = e.room_id"
            " LEFT JOIN users u ON u.id = e.created_by"
            f" WHERE {' AND '.join(where)} ORDER BY e.date", params,
        )
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Дата", "Категория", "Объект", "Номер", "Сумма", "Комментарий", "Кто добавил"])
    for r in rows:
        w.writerow([r["date"].strftime("%d.%m.%Y"), r["category_name"], r["property_name"] or "Общий",
                    r["room_name"] or "", str(r["amount"]).replace(".", ","), r["comment"], r["created_by_name"] or ""])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=expenses_{start}_{end}.csv"})


def _validate_property_room(conn, account_id: str, d: dict) -> tuple[str | None, str | None]:
    property_id = parse_uuid(d["property_id"], "Объект") if d.get("property_id") else None
    room_id = parse_uuid(d["room_id"], "Номер") if d.get("room_id") else None
    if property_id and not one(conn, "SELECT 1 FROM properties WHERE id = %s AND account_id = %s",
                                (property_id, account_id)):
        raise ApiError(404, "Объект не найден")
    if room_id:
        room = one(conn, "SELECT property_id FROM rooms WHERE id = %s AND account_id = %s", (room_id, account_id))
        if not room:
            raise ApiError(404, "Номер не найден")
        if property_id and str(room["property_id"]) != str(property_id):
            raise ApiError(422, "Номер принадлежит другому объекту")
        property_id = room["property_id"]
    return property_id, room_id


@api("manager")
def create_expense(c: Ctx):
    d = c.data
    exp_date = parse_date(d.get("date"), "Дата", "date") if d.get("date") else date.today()
    amount = parse_money(d.get("amount"), "Сумма")
    with tx() as conn:
        cat = _category(conn, c.account_id, d.get("category_id"))
        if cat["archived"]:
            raise ApiError(422, "Категория в архиве — выберите другую")
        property_id, room_id = _validate_property_room(conn, c.account_id, d)
        return one(
            conn,
            f"INSERT INTO expenses (account_id, property_id, room_id, category_id, date, amount, comment, created_by)"
            f" VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING {EXPENSE_COLS_PLAIN}",
            (c.account_id, property_id, room_id, cat["id"], exp_date, amount, opt_str(d, "comment", max_len=1000),
             c.p.user_id),
        )


@api("manager")
def update_expense(c: Ctx):
    eid = parse_uuid(c.path["id"])
    d = c.data
    with tx() as conn:
        e = one(conn, "SELECT * FROM expenses WHERE id = %s AND account_id = %s", (eid, c.account_id))
        if not e:
            raise ApiError(404, "Расход не найден")
        new = dict(e)
        if "date" in d:
            new["date"] = parse_date(d["date"], "Дата", "date")
        if "amount" in d:
            new["amount"] = parse_money(d["amount"], "Сумма")
        if "comment" in d:
            new["comment"] = opt_str(d, "comment", max_len=1000)
        if "category_id" in d:
            new["category_id"] = _category(conn, c.account_id, d["category_id"])["id"]
        if "property_id" in d or "room_id" in d:
            property_id, room_id = _validate_property_room(conn, c.account_id, {
                "property_id": d.get("property_id", str(e["property_id"]) if e["property_id"] else None),
                "room_id": d.get("room_id", str(e["room_id"]) if e["room_id"] else None),
            })
            new["property_id"], new["room_id"] = property_id, room_id
        return one(
            conn,
            f"UPDATE expenses SET property_id=%s, room_id=%s, category_id=%s, date=%s, amount=%s, comment=%s"
            f" WHERE id=%s RETURNING {EXPENSE_COLS_PLAIN}",
            (new["property_id"], new["room_id"], new["category_id"], new["date"], new["amount"], new["comment"], eid),
        )


@api("owner")
def delete_expense(c: Ctx):
    eid = parse_uuid(c.path["id"])
    with tx() as conn:
        if not run(conn, "DELETE FROM expenses WHERE id = %s AND account_id = %s", (eid, c.account_id)):
            raise ApiError(404, "Расход не найден")


# ---------- повторяющиеся расходы ----------

@api("manager")
def list_recurring(c: Ctx):
    with tx() as conn:
        return all_(
            conn,
            "SELECT rr.id, rr.property_id, rr.room_id, rr.category_id, rr.amount, rr.day_of_month, rr.comment,"
            " rr.active, cat.name AS category_name, cat.color AS category_color, p.name AS property_name,"
            " r.name AS room_name FROM expense_recurring_rules rr"
            " JOIN expense_categories cat ON cat.id = rr.category_id"
            " LEFT JOIN properties p ON p.id = rr.property_id LEFT JOIN rooms r ON r.id = rr.room_id"
            " WHERE rr.account_id = %s ORDER BY rr.active DESC, rr.day_of_month", (c.account_id,),
        )


@api("owner")
def create_recurring(c: Ctx):
    d = c.data
    day = parse_int(d.get("day_of_month"), "День месяца", 1)
    if day > 28:
        raise ApiError(422, "День месяца — от 1 до 28 (чтобы дата была в любом месяце)", {"field": "day_of_month"})
    amount = parse_money(d.get("amount"), "Сумма")
    with tx() as conn:
        cat = _category(conn, c.account_id, d.get("category_id"))
        property_id, room_id = _validate_property_room(conn, c.account_id, d)
        return one(
            conn,
            "INSERT INTO expense_recurring_rules (account_id, property_id, room_id, category_id, amount,"
            " day_of_month, comment, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (c.account_id, property_id, room_id, cat["id"], amount, day, opt_str(d, "comment", max_len=500),
             c.p.user_id),
        )


@api("owner")
def update_recurring(c: Ctx):
    rid = parse_uuid(c.path["id"])
    d = c.data
    sets, params = [], []
    if "active" in d:
        sets.append("active = %s"); params.append(bool(d["active"]))
    if "amount" in d:
        sets.append("amount = %s"); params.append(parse_money(d["amount"], "Сумма"))
    if "day_of_month" in d:
        day = parse_int(d["day_of_month"], "День месяца", 1)
        if day > 28:
            raise ApiError(422, "День месяца — от 1 до 28", {"field": "day_of_month"})
        sets.append("day_of_month = %s"); params.append(day)
    if "comment" in d:
        sets.append("comment = %s"); params.append(opt_str(d, "comment", max_len=500))
    if not sets and "category_id" not in d:
        raise ApiError(422, "Нечего сохранять")
    with tx() as conn:
        if "category_id" in d:
            cat = _category(conn, c.account_id, d["category_id"])
            sets.append("category_id = %s"); params.append(cat["id"])
        row = one(conn, f"UPDATE expense_recurring_rules SET {', '.join(sets)} WHERE id = %s AND account_id = %s"
                        " RETURNING *", (*params, rid, c.account_id))
    if not row:
        raise ApiError(404, "Шаблон не найден")
    return row


@api("owner")
def delete_recurring(c: Ctx):
    rid = parse_uuid(c.path["id"])
    with tx() as conn:
        if not run(conn, "DELETE FROM expense_recurring_rules WHERE id = %s AND account_id = %s",
                   (rid, c.account_id)):
            raise ApiError(404, "Шаблон не найден")


routes = [
    Route("/api/expense-categories", list_categories),
    Route("/api/expense-categories", create_category, methods=["POST"]),
    Route("/api/expense-categories/{id}", update_category, methods=["PATCH"]),
    Route("/api/expenses", list_expenses),
    Route("/api/expenses", create_expense, methods=["POST"]),
    Route("/api/expenses/export.csv", export_expenses),
    Route("/api/expenses/{id}", update_expense, methods=["PATCH"]),
    Route("/api/expenses/{id}", delete_expense, methods=["DELETE"]),
    Route("/api/expense-recurring", list_recurring),
    Route("/api/expense-recurring", create_recurring, methods=["POST"]),
    Route("/api/expense-recurring/{id}", update_recurring, methods=["PATCH"]),
    Route("/api/expense-recurring/{id}", delete_recurring, methods=["DELETE"]),
]
