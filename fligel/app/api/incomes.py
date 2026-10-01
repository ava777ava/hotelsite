"""Прочие доходы (не от проживания): категории и сами записи, выгрузка в CSV.

Устроено как расходы (app/api/expenses.py): свои категории, привязка к объекту или к номеру
либо общий доход на весь аккаунт. Права те же: смотреть и добавлять — администратор и владелец,
удалять и управлять категориями — только владелец.
"""
import csv
import io
from datetime import date
from decimal import Decimal

from starlette.responses import Response
from starlette.routing import Route

from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import csv_safe, opt_str, parse_color, parse_date, parse_int, parse_money, parse_uuid, req_str
from .base import Ctx, api
from .expenses import _date_range, _validate_property_room

INCOME_COLS_PLAIN = "id, property_id, room_id, category_id, date, amount, comment, created_at"
INCOME_COLS = "i.id, i.property_id, i.room_id, i.category_id, i.date, i.amount, i.comment, i.created_at"


def _category(conn, account_id: str, category_id) -> dict:
    cat = one(conn, "SELECT * FROM income_categories WHERE id = %s AND account_id = %s",
              (parse_uuid(category_id, "Категория"), account_id))
    if not cat:
        raise ApiError(404, "Категория не найдена")
    return cat


# ---------- категории ----------

@api("manager")
def list_categories(c: Ctx):
    with tx() as conn:
        where = "account_id = %s" if c.q.get("include_archived") == "1" else "account_id = %s AND NOT archived"
        return all_(conn, f"SELECT * FROM income_categories WHERE {where} ORDER BY sort_order, name",
                    (c.account_id,))


@api("owner")
def create_category(c: Ctx):
    name = req_str(c.data, "name", "Название категории", 100)
    color = parse_color(c.data, "color", "#2F5D50")
    with tx() as conn:
        if one(conn, "SELECT 1 FROM income_categories WHERE account_id = %s AND lower(name) = lower(%s)"
                     " AND NOT archived", (c.account_id, name)):
            raise ApiError(409, "Категория с таким названием уже есть")
        order = one(conn, "SELECT coalesce(max(sort_order), -1) + 1 AS n FROM income_categories"
                          " WHERE account_id = %s", (c.account_id,))["n"]
        return one(conn, "INSERT INTO income_categories (account_id, name, color, sort_order)"
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
        sets.append("color = %s"); params.append(parse_color(d, "color", "#2F5D50"))
    if "archived" in d:
        sets.append("archived = %s"); params.append(bool(d["archived"]))
    if "sort_order" in d:
        sets.append("sort_order = %s"); params.append(parse_int(d["sort_order"], "Порядок", 0))
    if not sets:
        raise ApiError(422, "Нечего сохранять")
    with tx() as conn:
        if new_name and one(conn, "SELECT 1 FROM income_categories WHERE account_id = %s AND lower(name) = lower(%s)"
                                  " AND NOT archived AND id <> %s", (c.account_id, new_name, cat_id)):
            raise ApiError(409, "Категория с таким названием уже есть")
        row = one(conn, f"UPDATE income_categories SET {', '.join(sets)} WHERE id = %s AND account_id = %s"
                        " RETURNING *", (*params, cat_id, c.account_id))
    if not row:
        raise ApiError(404, "Категория не найдена")
    return row


# ---------- доходы ----------

def _filters(c: Ctx):
    start, end = _date_range(c)
    where = ["i.account_id = %s"]
    params: list = [c.account_id]
    if c.q.get("property_id") == "none":
        where.append("i.property_id IS NULL")
    elif c.q.get("property_id"):
        where.append("i.property_id = %s")
        params.append(parse_uuid(c.q["property_id"], "Объект"))
    if c.q.get("room_id"):
        where.append("i.room_id = %s")
        params.append(parse_uuid(c.q["room_id"], "Номер"))
    if c.q.get("category_id"):
        where.append("i.category_id = %s")
        params.append(parse_uuid(c.q["category_id"], "Категория"))
    where.append("i.date >= %s AND i.date < %s")
    params += [start, end]
    return start, end, where, params


_SELECT_ROWS = (
    "SELECT {cols}, cat.name AS category_name, cat.color AS category_color, p.name AS property_name,"
    " r.name AS room_name, u.name AS created_by_name FROM incomes i"
    " JOIN income_categories cat ON cat.id = i.category_id"
    " LEFT JOIN properties p ON p.id = i.property_id LEFT JOIN rooms r ON r.id = i.room_id"
    " LEFT JOIN users u ON u.id = i.created_by WHERE {where} ORDER BY {order}"
)


@api("manager")
def list_incomes(c: Ctx):
    start, end, where, params = _filters(c)
    with tx() as conn:
        rows = all_(conn, _SELECT_ROWS.format(cols=INCOME_COLS, where=" AND ".join(where),
                                              order="i.date DESC, i.created_at DESC") + " LIMIT 2000", params)
    total = sum((Decimal(r["amount"]) for r in rows), Decimal("0"))
    by_cat: dict[str, dict] = {}
    for r in rows:
        s = by_cat.setdefault(str(r["category_id"]), {
            "category_id": r["category_id"], "category_name": r["category_name"],
            "category_color": r["category_color"], "amount": Decimal("0"), "count": 0})
        s["amount"] += Decimal(r["amount"])
        s["count"] += 1
    return {"from": start, "to": end, "rows": rows, "total": total,
            "by_category": sorted(by_cat.values(), key=lambda s: -s["amount"])}


@api("manager")
def export_incomes(c: Ctx):
    start, end, where, params = _filters(c)
    with tx() as conn:
        rows = all_(conn, _SELECT_ROWS.format(cols=INCOME_COLS, where=" AND ".join(where), order="i.date"), params)
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Дата", "Категория", "Объект", "Номер", "Сумма", "Комментарий", "Кто добавил"])
    for r in rows:
        w.writerow([r["date"].strftime("%d.%m.%Y"), csv_safe(r["category_name"]),
                    csv_safe(r["property_name"] or "Общий"), csv_safe(r["room_name"] or ""),
                    str(r["amount"]).replace(".", ","), csv_safe(r["comment"]), csv_safe(r["created_by_name"] or "")])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=incomes_{start}_{end}.csv"})


@api("manager")
def create_income(c: Ctx):
    d = c.data
    inc_date = parse_date(d.get("date"), "Дата", "date") if d.get("date") else date.today()
    amount = parse_money(d.get("amount"), "Сумма")
    with tx() as conn:
        cat = _category(conn, c.account_id, d.get("category_id"))
        if cat["archived"]:
            raise ApiError(422, "Категория в архиве — выберите другую")
        property_id, room_id = _validate_property_room(conn, c.account_id, d)
        return one(
            conn,
            f"INSERT INTO incomes (account_id, property_id, room_id, category_id, date, amount, comment, created_by)"
            f" VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING {INCOME_COLS_PLAIN}",
            (c.account_id, property_id, room_id, cat["id"], inc_date, amount, opt_str(d, "comment", max_len=1000),
             c.p.user_id),
        )


@api("manager")
def update_income(c: Ctx):
    iid = parse_uuid(c.path["id"])
    d = c.data
    with tx() as conn:
        e = one(conn, "SELECT * FROM incomes WHERE id = %s AND account_id = %s FOR UPDATE", (iid, c.account_id))
        if not e:
            raise ApiError(404, "Доход не найден")
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
            f"UPDATE incomes SET property_id=%s, room_id=%s, category_id=%s, date=%s, amount=%s, comment=%s"
            f" WHERE id=%s RETURNING {INCOME_COLS_PLAIN}",
            (new["property_id"], new["room_id"], new["category_id"], new["date"], new["amount"], new["comment"], iid),
        )


@api("owner")
def delete_income(c: Ctx):
    iid = parse_uuid(c.path["id"])
    with tx() as conn:
        if not run(conn, "DELETE FROM incomes WHERE id = %s AND account_id = %s", (iid, c.account_id)):
            raise ApiError(404, "Доход не найден")


routes = [
    Route("/api/income-categories", list_categories),
    Route("/api/income-categories", create_category, methods=["POST"]),
    Route("/api/income-categories/{id}", update_category, methods=["PATCH"]),
    Route("/api/incomes", list_incomes),
    Route("/api/incomes", create_income, methods=["POST"]),
    Route("/api/incomes/export.csv", export_incomes),
    Route("/api/incomes/{id}", update_income, methods=["PATCH"]),
    Route("/api/incomes/{id}", delete_income, methods=["DELETE"]),
]
