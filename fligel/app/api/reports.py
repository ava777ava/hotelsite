"""Финансовая аналитика: доходы по ночам, расходы по дате, показатели, сравнения периодов.

Общие расходы (без объекта, expenses.property_id IS NULL) при разбивке по объектам
делятся пропорционально числу номеров — от общего числа номеров аккаунта, а не только
просматриваемых объектов, чтобы доли по всем объектам в сумме всегда давали 100%.
"""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from starlette.responses import Response
from starlette.routing import Route

from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import parse_date, parse_money, parse_uuid
from .base import Ctx, api
from .channels import CHANNELS
from .common import selected_property

SOURCE_LABELS = {"manual": "Вручную", "direct": "Сайт", "avito": "Авито", "yandex": "Яндекс Путешествия",
                  "sutochno": "Суточно.ру", "ostrovok": "Островок", "other": "Другое"}


# ---------- периоды ----------

def _period(c: Ctx) -> tuple[date, date]:
    if c.q.get("from") and c.q.get("to"):
        start = parse_date(c.q["from"], "Начало периода")
        end = parse_date(c.q["to"], "Конец периода")
    else:
        today = date.today()
        start = today.replace(day=1)
        end = _add_months(start, 1)
    if end <= start:
        raise ApiError(422, "Конец периода должен быть позже начала")
    if (end - start).days > 400:
        raise ApiError(422, "Слишком длинный период (максимум 400 дней)")
    return start, end


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    return date(y, m % 12 + 1, 1)


def _shift_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 февраля
        return d.replace(year=d.year + n, day=28)


def _delta(cur, prev) -> float | None:
    if not prev:
        return None
    return round(float((cur - prev) * 100 / prev), 1)


# ---------- вспомогательные выборки ----------

def _rooms_count(conn, property_ids: list[str]) -> int:
    if not property_ids:
        return 0
    return one(conn, "SELECT count(*) AS n FROM rooms WHERE property_id = ANY(%s::uuid[])", (property_ids,))["n"]


def _overlap_rows(conn, account_id: str, property_ids: list[str], start: date, end: date) -> list[dict]:
    return all_(
        conn,
        "SELECT room_id, source, status, check_in, check_out, total_price, paid_amount,"
        " (least(check_out, %s::date) - greatest(check_in, %s::date)) AS nights_in,"
        " (check_out - check_in) AS nights FROM bookings"
        " WHERE account_id = %s AND property_id = ANY(%s::uuid[])"
        " AND status IN ('confirmed', 'pending', 'blocked') AND check_in < %s AND check_out > %s",
        (end, start, account_id, property_ids, end, start),
    )


def _booking_metrics(rows: list[dict], rooms: int, days: int) -> dict:
    sold = blocked = 0
    revenue = due = Decimal("0")
    by_source: dict[str, dict] = {}
    by_room: dict[str, dict] = {}
    for r in rows:
        if r["status"] == "blocked":
            blocked += r["nights_in"]
            continue
        share = Decimal(r["total_price"]) * r["nights_in"] / r["nights"]
        sold += r["nights_in"]
        revenue += share
        if r["status"] in ("confirmed", "pending"):
            due += max((Decimal(r["total_price"]) - Decimal(r["paid_amount"])) * r["nights_in"] / r["nights"],
                       Decimal("0"))
        s = by_source.setdefault(r["source"], {"source": r["source"], "nights": 0, "revenue": Decimal("0"),
                                               "bookings": 0})
        s["nights"] += r["nights_in"]; s["revenue"] += share; s["bookings"] += 1
        rm = by_room.setdefault(str(r["room_id"]), {"nights": 0, "revenue": Decimal("0")})
        rm["nights"] += r["nights_in"]; rm["revenue"] += share
    available = rooms * days
    return {
        "room_nights": available, "sold_nights": sold, "blocked_nights": blocked,
        "occupancy": round(sold * 100 / available, 1) if available else 0.0,
        "revenue": revenue, "due": due,
        "adr": (revenue / sold) if sold else Decimal("0"),
        "revpar": (revenue / available) if available else Decimal("0"),
        "by_source": by_source, "by_room": by_room,
    }


def _arrivals_metrics(conn, account_id: str, property_ids: list[str], start: date, end: date) -> tuple[float, float]:
    rows = all_(conn, "SELECT status, (check_out - check_in) AS nights FROM bookings"
                      " WHERE account_id = %s AND property_id = ANY(%s::uuid[])"
                      " AND check_in >= %s AND check_in < %s", (account_id, property_ids, start, end))
    total = len(rows)
    cancelled = sum(1 for r in rows if r["status"] == "cancelled")
    active_nights = [r["nights"] for r in rows if r["status"] != "cancelled"]
    avg_stay = round(sum(active_nights) / len(active_nights), 1) if active_nights else 0.0
    cancellation_rate = round(cancelled * 100 / total, 1) if total else 0.0
    return avg_stay, cancellation_rate


def _expenses_total(conn, account_id: str, property_ids: list[str], scope_rooms: int, total_rooms: int,
                    start: date, end: date) -> Decimal:
    direct = one(conn, "SELECT coalesce(sum(amount), 0) AS n FROM expenses WHERE account_id = %s"
                       " AND property_id = ANY(%s::uuid[]) AND date >= %s AND date < %s",
                (account_id, property_ids, start, end))["n"]
    shared = one(conn, "SELECT coalesce(sum(amount), 0) AS n FROM expenses WHERE account_id = %s"
                       " AND property_id IS NULL AND date >= %s AND date < %s", (account_id, start, end))["n"]
    allocated = (Decimal(shared) * scope_rooms / total_rooms) if total_rooms else Decimal("0")
    return Decimal(direct) + allocated


def _expenses_by_category(conn, account_id: str, property_ids: list[str], scope_rooms: int, total_rooms: int,
                          start: date, end: date) -> list[dict]:
    direct_rows = all_(
        conn,
        "SELECT e.category_id, cat.name, cat.color, sum(e.amount) AS amount FROM expenses e"
        " JOIN expense_categories cat ON cat.id = e.category_id"
        " WHERE e.account_id = %s AND e.property_id = ANY(%s::uuid[]) AND e.date >= %s AND e.date < %s"
        " GROUP BY e.category_id, cat.name, cat.color", (account_id, property_ids, start, end),
    )
    shared_rows = all_(
        conn,
        "SELECT e.category_id, cat.name, cat.color, sum(e.amount) AS amount FROM expenses e"
        " JOIN expense_categories cat ON cat.id = e.category_id"
        " WHERE e.account_id = %s AND e.property_id IS NULL AND e.date >= %s AND e.date < %s"
        " GROUP BY e.category_id, cat.name, cat.color", (account_id, start, end),
    )
    result: dict[str, dict] = {}
    for r in direct_rows:
        result[str(r["category_id"])] = {"category_id": r["category_id"], "name": r["name"], "color": r["color"],
                                         "amount": Decimal(r["amount"])}
    ratio = (Decimal(scope_rooms) / total_rooms) if total_rooms else Decimal("0")
    for r in shared_rows:
        key = str(r["category_id"])
        entry = result.setdefault(key, {"category_id": r["category_id"], "name": r["name"], "color": r["color"],
                                        "amount": Decimal("0")})
        entry["amount"] += Decimal(r["amount"]) * ratio
    return sorted(result.values(), key=lambda x: -x["amount"])


def _weekday_occupancy(rows: list[dict], rooms: int, start: date, end: date) -> list[dict]:
    buckets = {i: {"available": 0, "sold": 0} for i in range(7)}
    d = start
    while d < end:
        buckets[(d.weekday() + 1) % 7]["available"] += rooms  # переводим в JS-нумерацию: 0 = воскресенье
        d += timedelta(days=1)
    for r in rows:
        if r["status"] == "blocked":
            continue
        d = max(r["check_in"], start)
        stop = min(r["check_out"], end)
        while d < stop:
            buckets[(d.weekday() + 1) % 7]["sold"] += 1
            d += timedelta(days=1)
    return [{"weekday": i, "occupancy": round(b["sold"] * 100 / b["available"], 1) if b["available"] else 0.0}
            for i, b in sorted(buckets.items())]


def _period_summary(conn, account_id: str, property_ids: list[str], scope_rooms: int, total_rooms: int,
                    start: date, end: date) -> dict:
    rows = _overlap_rows(conn, account_id, property_ids, start, end)
    days = (end - start).days
    m = _booking_metrics(rows, scope_rooms, days)
    expenses = _expenses_total(conn, account_id, property_ids, scope_rooms, total_rooms, start, end)
    revenue = m["revenue"]
    profit = revenue - expenses
    return {
        "revenue": revenue, "expenses": expenses, "profit": profit,
        "margin": round(float(profit * 100 / revenue), 1) if revenue else None,
        "occupancy": m["occupancy"], "adr": m["adr"], "revpar": m["revpar"], "due": m["due"],
        "room_nights": m["room_nights"], "sold_nights": m["sold_nights"],
        "raw_rows": rows, "by_source_raw": m["by_source"], "by_room_raw": m["by_room"],
    }


def _cmp_block(main: dict, other: dict) -> dict:
    return {
        "revenue": other["revenue"], "expenses": other["expenses"], "profit": other["profit"],
        "occupancy": other["occupancy"],
        "revenue_delta": _delta(main["revenue"], other["revenue"]),
        "expenses_delta": _delta(main["expenses"], other["expenses"]),
        "profit_delta": _delta(main["profit"], other["profit"]),
        "occupancy_delta": _delta(Decimal(str(main["occupancy"])), Decimal(str(other["occupancy"]))),
    }


# ---------- сборка отчёта ----------

def _build_report(c: Ctx) -> dict:
    start, end = _period(c)
    with tx() as conn:
        prop_id = parse_uuid(c.q["property_id"], "Объект") if c.q.get("property_id") else None
        if prop_id:
            selected_property(conn, c.account_id, prop_id)
        all_properties = all_(conn, "SELECT id, name FROM properties WHERE account_id = %s ORDER BY created_at",
                              (c.account_id,))
        all_property_ids = [p["id"] for p in all_properties]
        scope_ids = [prop_id] if prop_id else all_property_ids
        total_rooms = _rooms_count(conn, all_property_ids)
        scope_rooms = _rooms_count(conn, scope_ids)

        main = _period_summary(conn, c.account_id, scope_ids, scope_rooms, total_rooms, start, end)
        days = (end - start).days
        prev = _period_summary(conn, c.account_id, scope_ids, scope_rooms, total_rooms,
                               start - timedelta(days=days), start)
        prev_year = _period_summary(conn, c.account_id, scope_ids, scope_rooms, total_rooms,
                                    _shift_years(start, -1), _shift_years(end, -1))
        avg_stay, cancellation_rate = _arrivals_metrics(conn, c.account_id, scope_ids, start, end)

        room_meta = {
            str(r["id"]): r for r in all_(
                conn,
                "SELECT r.id, r.name, rt.name AS room_type_name, p.name AS property_name FROM rooms r"
                " JOIN room_types rt ON rt.id = r.room_type_id JOIN properties p ON p.id = r.property_id"
                " WHERE r.property_id = ANY(%s::uuid[])", (scope_ids,),
            )
        }
        by_room_map = {rid: {"nights": 0, "revenue": Decimal("0")} for rid in room_meta}
        for rid, agg in main["by_room_raw"].items():
            e = by_room_map.setdefault(rid, {"nights": 0, "revenue": Decimal("0")})
            e["nights"] += agg["nights"]; e["revenue"] += agg["revenue"]
        by_room = []
        for rid, e in by_room_map.items():
            meta = room_meta.get(rid, {})
            by_room.append({
                "room_id": rid, "room_name": meta.get("name", "—"), "room_type_name": meta.get("room_type_name", ""),
                "property_name": meta.get("property_name", ""), "nights": e["nights"], "revenue": e["revenue"],
                "occupancy": round(e["nights"] * 100 / days, 1) if days else 0.0,
            })
        by_room.sort(key=lambda x: -x["revenue"])

        by_room_type_map: dict[str, dict] = {}
        for b in by_room:
            key = b["room_type_name"]
            t = by_room_type_map.setdefault(key, {"room_type_name": key, "rooms": 0, "nights": 0,
                                                   "revenue": Decimal("0")})
            t["rooms"] += 1; t["nights"] += b["nights"]; t["revenue"] += b["revenue"]
        by_room_type = sorted(by_room_type_map.values(), key=lambda x: -x["revenue"])

        commissions = {r["channel"]: r["percent"] for r in all_(
            conn, "SELECT channel, percent FROM channel_commissions WHERE account_id = %s", (c.account_id,))}
        by_source = []
        for s in main["by_source_raw"].values():
            pct = Decimal(commissions.get(s["source"], 0))
            commission_amount = (s["revenue"] * pct / 100) if pct else Decimal("0")
            by_source.append({**s, "label": SOURCE_LABELS.get(s["source"], s["source"]),
                               "commission_percent": pct, "commission_amount": commission_amount,
                               "net_revenue": s["revenue"] - commission_amount})
        by_source.sort(key=lambda x: -x["revenue"])

        by_expense_category = _expenses_by_category(conn, c.account_id, scope_ids, scope_rooms, total_rooms,
                                                     start, end)

        by_property = None
        if not prop_id and len(all_properties) > 1:
            by_property = []
            for p in all_properties:
                p_rooms = _rooms_count(conn, [p["id"]])
                ps = _period_summary(conn, c.account_id, [p["id"]], p_rooms, total_rooms, start, end)
                by_property.append({"property_id": p["id"], "property_name": p["name"], "revenue": ps["revenue"],
                                     "expenses": ps["expenses"], "profit": ps["profit"],
                                     "occupancy": ps["occupancy"], "rooms": p_rooms})
            by_property.sort(key=lambda x: -x["revenue"])

        weekday = _weekday_occupancy(main["raw_rows"], scope_rooms, start, end)

        monthly = []
        cursor = _add_months(date(start.year, start.month, 1), -11)
        for _ in range(12):
            m_end = _add_months(cursor, 1)
            ms = _period_summary(conn, c.account_id, scope_ids, scope_rooms, total_rooms, cursor, m_end)
            monthly.append({"month": cursor.isoformat(), "revenue": ms["revenue"], "expenses": ms["expenses"],
                            "profit": ms["profit"]})
            cursor = m_end

    return {
        "from": start, "to": end, "property_id": prop_id,
        "totals": {
            "revenue": main["revenue"], "expenses": main["expenses"], "profit": main["profit"],
            "margin": main["margin"], "occupancy": main["occupancy"], "adr": main["adr"], "revpar": main["revpar"],
            "avg_stay": avg_stay, "cancellation_rate": cancellation_rate, "due_amount": main["due"],
            "rooms": scope_rooms, "room_nights": main["room_nights"], "sold_nights": main["sold_nights"],
        },
        "compare_prev_period": _cmp_block(main, prev),
        "compare_prev_year": _cmp_block(main, prev_year),
        "by_property": by_property,
        "by_room_type": by_room_type,
        "by_room": by_room,
        "by_source": by_source,
        "by_expense_category": by_expense_category,
        "monthly": monthly,
        "weekday_occupancy": weekday,
        "share_note": "Общие расходы (без привязки к объекту) делятся между объектами "
                      "пропорционально числу номеров.",
    }


@api("manager")
def report(c: Ctx):
    return _build_report(c)


def _num(v) -> str:
    if v is None:
        return ""
    return str(v).replace(".", ",")


@api("manager")
def export_report(c: Ctx):
    data = _build_report(c)
    t = data["totals"]
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Отчёт", f"{data['from']}", f"{data['to']}"])
    w.writerow([])
    w.writerow(["Показатель", "Значение"])
    for label, value in [
        ("Выручка", t["revenue"]), ("Расходы", t["expenses"]), ("Прибыль", t["profit"]),
        ("Рентабельность, %", t["margin"]), ("Загрузка, %", t["occupancy"]), ("ADR", t["adr"]),
        ("RevPAR", t["revpar"]), ("Средний срок проживания, ночей", t["avg_stay"]),
        ("Доля отмен, %", t["cancellation_rate"]), ("Гости должны доплатить", t["due_amount"]),
    ]:
        w.writerow([label, _num(value)])
    w.writerow([])
    w.writerow(["По источникам"])
    w.writerow(["Источник", "Броней", "Ночей", "Выручка", "Комиссия, %", "Комиссия", "Чистая выручка"])
    for s in data["by_source"]:
        w.writerow([s["label"], s["bookings"], s["nights"], _num(s["revenue"]), _num(s["commission_percent"]),
                    _num(s["commission_amount"]), _num(s["net_revenue"])])
    w.writerow([])
    w.writerow(["По категориям расходов"])
    w.writerow(["Категория", "Сумма"])
    for x in data["by_expense_category"]:
        w.writerow([x["name"], _num(x["amount"])])
    w.writerow([])
    w.writerow(["По номерам"])
    w.writerow(["Номер", "Категория", "Объект", "Ночей", "Загрузка, %", "Выручка"])
    for r in data["by_room"]:
        w.writerow([r["room_name"], r["room_type_name"], r["property_name"], r["nights"], _num(r["occupancy"]),
                    _num(r["revenue"])])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=report_{data['from']}_{data['to']}.csv"})


# ---------- комиссии площадок ----------

@api("manager")
def get_commissions(c: Ctx):
    with tx() as conn:
        rows = all_(conn, "SELECT channel, percent FROM channel_commissions WHERE account_id = %s", (c.account_id,))
    have = {r["channel"]: r["percent"] for r in rows}
    return [{"channel": ch, "percent": have.get(ch, Decimal("0"))} for ch in CHANNELS]


@api("manager")
def set_commissions(c: Ctx):
    items = c.data.get("items") or []
    if not isinstance(items, list):
        raise ApiError(422, "Неверный формат")
    with tx() as conn:
        for it in items:
            ch = it.get("channel")
            if ch not in CHANNELS:
                continue
            pct = parse_money(it.get("percent"), "Комиссия")
            if pct > 100:
                raise ApiError(422, "Комиссия не может быть больше 100%")
            run(conn, "INSERT INTO channel_commissions (account_id, channel, percent) VALUES (%s, %s, %s)"
                      " ON CONFLICT (account_id, channel) DO UPDATE SET percent = EXCLUDED.percent",
                (c.account_id, ch, pct))
    return {"ok": True}


routes = [
    Route("/api/reports", report),
    Route("/api/reports/export.csv", export_report),
    Route("/api/channel-commissions", get_commissions),
    Route("/api/channel-commissions", set_commissions, methods=["PUT"]),
]
