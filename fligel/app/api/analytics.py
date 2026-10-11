"""Аналитика вперёд и по каналам: прогноз загрузки/выручки на 30/60/90 дней (и «год назад»), темп бронирований,
окно бронирования и средний срок проживания, доходность каналов, сводка для бухгалтера (с CSV)."""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from starlette.responses import Response
from starlette.routing import Route

from ..db import all_, one, tx
from ..errors import ApiError
from ..util import csv_safe, parse_date, parse_uuid
from .base import Ctx, api
from .common import selected_property
from .money import METHODS
from .reports import SOURCE_LABELS, _booking_metrics, _delta, _money, _rooms_count, _shift_years

HORIZONS = (30, 60, 90)


def _scope(conn, c: Ctx) -> list[str]:
    """Объекты в отчёте: выбранный или все объекты аккаунта."""
    if c.q.get("property_id"):
        selected_property(conn, c.account_id, c.q.get("property_id"))
        return [parse_uuid(c.q["property_id"], "Объект")]
    return [str(r["id"]) for r in all_(conn, "SELECT id FROM properties WHERE account_id = %s ORDER BY created_at", (c.account_id,))]


def _period(c: Ctx, default_days: int = 90) -> tuple[date, date]:
    if c.q.get("from") and c.q.get("to"):
        start, end = parse_date(c.q["from"], "Начало периода"), parse_date(c.q["to"], "Конец периода")
    else:
        end = date.today() + timedelta(days=1)
        start = end - timedelta(days=default_days)
    if end <= start:
        raise ApiError(422, "Конец периода должен быть позже начала")
    if (end - start).days > 400:
        raise ApiError(422, "Слишком длинный период (максимум 400 дней)")
    return start, end


# ---------- прогноз вперёд ----------

def _window(conn, account_id, pids, rooms, start: date, end: date, created_before=None) -> dict:
    sql = ("SELECT room_id, source, status, check_in, check_out, total_price, paid_amount,"
           " (least(check_out, %s::date) - greatest(check_in, %s::date)) AS nights_in, (check_out - check_in) AS nights"
           " FROM bookings WHERE account_id = %s AND property_id = ANY(%s::uuid[]) AND status IN ('confirmed', 'pending', 'blocked')"
           " AND check_in < %s AND check_out > %s")
    params = [end, start, account_id, pids, end, start]
    if created_before is not None:
        sql += " AND created_at <= %s"
        params.append(created_before)
    m = _booking_metrics(all_(conn, sql, params), rooms, (end - start).days)
    return {"occupancy": m["occupancy"], "revenue": m["revenue"], "sold_nights": m["sold_nights"], "room_nights": m["room_nights"], "adr": m["adr"]}


@api("manager")
def forecast(c: Ctx):
    """Что уже забронировано на ближайшие 30/60/90 дней и как это выглядело год назад — на ту же дату («темп») и по итогам."""
    today = date.today()
    with tx() as conn:
        pids = _scope(conn, c)
        rooms = _rooms_count(conn, pids)
        year_ago_moment = one(conn, "SELECT now() - interval '1 year' AS t")["t"]
        # «Темп» год назад можно посчитать, только если система работала уже тогда (брони созданы больше года назад)
        pace_ok = bool(one(conn, "SELECT 1 FROM bookings WHERE account_id = %s AND property_id = ANY(%s::uuid[]) AND created_at <= %s LIMIT 1",
                           (c.account_id, pids, year_ago_moment)))
        out = []
        for n in HORIZONS:
            start, end = today, today + timedelta(days=n)
            cur = _window(conn, c.account_id, pids, rooms, start, end)
            ys, ye = _shift_years(start, -1), _shift_years(end, -1)
            final = _window(conn, c.account_id, pids, rooms, ys, ye)
            pace = _window(conn, c.account_id, pids, rooms, ys, ye, year_ago_moment) if pace_ok else None
            has_final = final["sold_nights"] > 0
            out.append({"days": n, "from": start, "to": end, **cur,
                        "year_ago_pace": pace, "year_ago_final": final if has_final else None,
                        "revenue_vs_pace": _delta(cur["revenue"], pace["revenue"]) if pace else None,
                        "revenue_vs_final": _delta(cur["revenue"], final["revenue"]) if has_final else None,
                        "occupancy_vs_pace": round(cur["occupancy"] - pace["occupancy"], 1) if pace else None})
    return {"horizons": out, "rooms": rooms, "pace_available": pace_ok,
            "note": "Выручка считается по ночам внутри периода. Для сравнения «на ту же дату год назад» нужны брони, созданные в системе больше года назад."}


# ---------- темп бронирований ----------

@api("manager")
def pace(c: Ctx):
    """Сколько броней появилось за последние 7 дней против предыдущих 7: по источникам и по дням."""
    today = date.today()
    cur_start, prev_start, end = today - timedelta(days=6), today - timedelta(days=13), today + timedelta(days=1)
    with tx() as conn:
        pids = _scope(conn, c)

        def by_source(a: date, b: date) -> dict:
            rows = all_(conn, "SELECT source, count(*) AS bookings, coalesce(sum(check_out - check_in), 0) AS nights,"
                              " coalesce(sum(total_price), 0) AS revenue FROM bookings WHERE account_id = %s"
                              " AND property_id = ANY(%s::uuid[]) AND status IN ('confirmed', 'pending')"
                              " AND created_at::date >= %s AND created_at::date < %s GROUP BY source", (c.account_id, pids, a, b))
            return {r["source"]: r for r in rows}

        cur, prev = by_source(cur_start, end), by_source(prev_start, cur_start)
        daily = all_(conn, "SELECT created_at::date AS day, count(*) AS bookings FROM bookings WHERE account_id = %s"
                           " AND property_id = ANY(%s::uuid[]) AND status IN ('confirmed', 'pending') AND created_at::date >= %s"
                           " AND created_at::date < %s GROUP BY 1 ORDER BY 1", (c.account_id, pids, prev_start, end))
    by_day = {r["day"]: r["bookings"] for r in daily}
    series = [{"day": prev_start + timedelta(days=i), "bookings": by_day.get(prev_start + timedelta(days=i), 0)} for i in range(14)]
    sources = []
    for s in sorted(set(cur) | set(prev), key=lambda k: -(cur.get(k, {}).get("bookings", 0) + prev.get(k, {}).get("bookings", 0))):
        a, b = cur.get(s, {}), prev.get(s, {})
        sources.append({"source": s, "label": SOURCE_LABELS.get(s, s), "bookings": a.get("bookings", 0), "prev_bookings": b.get("bookings", 0),
                        "nights": a.get("nights", 0), "revenue": a.get("revenue", Decimal("0")), "prev_revenue": b.get("revenue", Decimal("0"))})
    tot = lambda d, k: sum((v.get(k, 0) for v in d.values()), 0)  # noqa: E731
    return {"from": cur_start, "to": today, "prev_from": prev_start, "prev_to": cur_start - timedelta(days=1),
            "total": {"bookings": tot(cur, "bookings"), "prev_bookings": tot(prev, "bookings"), "nights": tot(cur, "nights"),
                      "revenue": tot(cur, "revenue"), "prev_revenue": tot(prev, "revenue")},
            "sources": sources, "daily": series}


# ---------- окно бронирования и срок проживания ----------

LEAD_BUCKETS = (("в день заезда или накануне", 0, 1), ("за 2–7 дней", 2, 7), ("за 8–30 дней", 8, 30), ("за 31–90 дней", 31, 90), ("раньше чем за 90 дней", 91, 10 ** 6))


@api("manager")
def lead_time(c: Ctx):
    """За сколько дней до заезда бронируют и на сколько ночей живут — по каналам. Брони с площадок через календарь
    считаются от момента, когда они появились в системе (площадка сообщает только занятость), и выглядят «поздними»."""
    start, end = _period(c)
    with tx() as conn:
        pids = _scope(conn, c)
        rows = all_(conn, "SELECT source, count(*) AS bookings, avg(greatest(check_in - created_at::date, 0)) AS lead,"
                          " avg(check_out - check_in) AS stay, sum(check_out - check_in) AS nights FROM bookings"
                          " WHERE account_id = %s AND property_id = ANY(%s::uuid[]) AND status IN ('confirmed', 'pending')"
                          " AND check_in >= %s AND check_in < %s GROUP BY source ORDER BY count(*) DESC", (c.account_id, pids, start, end))
        leads = [r["lead"] for r in all_(conn, "SELECT greatest(check_in - created_at::date, 0) AS lead FROM bookings WHERE account_id = %s"
                                                " AND property_id = ANY(%s::uuid[]) AND status IN ('confirmed', 'pending')"
                                                " AND check_in >= %s AND check_in < %s", (c.account_id, pids, start, end))]
    total = sum(r["bookings"] for r in rows)
    buckets = [{"label": label, "bookings": sum(1 for x in leads if lo <= x <= hi)} for label, lo, hi in LEAD_BUCKETS]
    return {"from": start, "to": end,
            "overall": {"bookings": total, "lead": round(sum(leads) / len(leads), 1) if leads else None,
                        "stay": round(float(sum(r["stay"] * r["bookings"] for r in rows) / total), 1) if total else None},
            "by_source": [{"source": r["source"], "label": SOURCE_LABELS.get(r["source"], r["source"]), "bookings": r["bookings"],
                           "lead": round(float(r["lead"]), 1), "stay": round(float(r["stay"]), 1)} for r in rows],
            "buckets": buckets}


# ---------- доходность каналов ----------

@api("manager")
def channels(c: Ctx):
    """По каналам за период (по датам заезда): выручка, комиссия, чистая выручка, средняя цена ночи, доля отмен."""
    start, end = _period(c, 90)
    with tx() as conn:
        pids = _scope(conn, c)
        rows = all_(conn, "SELECT source, count(*) FILTER (WHERE status IN ('confirmed', 'pending')) AS bookings,"
                          " count(*) FILTER (WHERE status = 'cancelled') AS cancelled,"
                          " coalesce(sum(check_out - check_in) FILTER (WHERE status IN ('confirmed', 'pending')), 0) AS nights,"
                          " coalesce(sum(total_price) FILTER (WHERE status IN ('confirmed', 'pending')), 0) AS revenue FROM bookings"
                          " WHERE account_id = %s AND property_id = ANY(%s::uuid[]) AND status <> 'blocked' AND check_in >= %s AND check_in < %s"
                          " GROUP BY source", (c.account_id, pids, start, end))
        comm = {r["channel"]: Decimal(r["percent"]) for r in all_(conn, "SELECT channel, percent FROM channel_commissions WHERE account_id = %s", (c.account_id,))}
    items = []
    for r in rows:
        pct = comm.get(r["source"], Decimal("0"))
        revenue = Decimal(r["revenue"])
        fee = _money(revenue * pct / 100) if pct else Decimal("0")
        total = r["bookings"] + r["cancelled"]
        nights = r["nights"]
        items.append({"source": r["source"], "label": SOURCE_LABELS.get(r["source"], r["source"]), "bookings": r["bookings"], "cancelled": r["cancelled"],
                      "cancel_share": round(r["cancelled"] * 100 / total, 1) if total else 0.0, "nights": nights, "revenue": revenue,
                      "commission_percent": pct, "commission": fee, "net_revenue": revenue - fee,
                      "avg_price": _money(revenue / nights) if nights else Decimal("0"),
                      "net_avg_price": _money((revenue - fee) / nights) if nights else Decimal("0")})
    items.sort(key=lambda x: -x["net_revenue"])
    return {"from": start, "to": end, "items": items,
            "totals": {"revenue": sum((x["revenue"] for x in items), Decimal("0")), "commission": sum((x["commission"] for x in items), Decimal("0")),
                       "net_revenue": sum((x["net_revenue"] for x in items), Decimal("0"))},
            "note": "Комиссию площадок задайте в «Отчёты → Комиссии». Если для канала комиссия 0 %, чистая выручка равна выручке."}


# ---------- сводка для бухгалтера ----------

def _accountant(conn, c: Ctx, start: date, end: date) -> dict:
    pids = _scope(conn, c)
    filtered = bool(c.q.get("property_id"))
    pay = all_(conn, "SELECT p.method, coalesce(sum(p.amount) FILTER (WHERE p.kind = 'payment'), 0) AS payments,"
                     " coalesce(sum(p.amount) FILTER (WHERE p.kind = 'refund'), 0) AS refunds FROM booking_payments p"
                     " JOIN bookings b ON b.id = p.booking_id WHERE p.account_id = %s AND b.property_id = ANY(%s::uuid[])"
                     " AND p.paid_on >= %s AND p.paid_on < %s GROUP BY p.method", (c.account_id, pids, start, end))
    by_method = [{"method": m, "label": label, "payments": Decimal("0"), "refunds": Decimal("0"), "net": Decimal("0")} for m, label in METHODS.items()]
    for r in pay:
        row = next(x for x in by_method if x["method"] == r["method"])
        row.update(payments=Decimal(r["payments"]), refunds=Decimal(r["refunds"]), net=Decimal(r["payments"]) - Decimal(r["refunds"]))
    by_method = [x for x in by_method if x["payments"] or x["refunds"]]
    scope_sql = "(e.property_id = ANY(%s::uuid[]))" if filtered else "(e.property_id = ANY(%s::uuid[]) OR e.property_id IS NULL)"

    def flow(table, cat):
        return all_(conn, f"SELECT cat.name, sum(e.amount) AS amount, count(*) AS n FROM {table} e JOIN {cat} cat ON cat.id = e.category_id"
                          f" WHERE e.account_id = %s AND {scope_sql} AND e.date >= %s AND e.date < %s GROUP BY cat.name ORDER BY sum(e.amount) DESC",
                    (c.account_id, pids, start, end))

    income = flow("incomes", "income_categories")
    expense = flow("expenses", "expense_categories")
    receipts = sum((x["net"] for x in by_method), Decimal("0"))
    other = sum((Decimal(x["amount"]) for x in income), Decimal("0"))
    spent = sum((Decimal(x["amount"]) for x in expense), Decimal("0"))
    return {"from": start, "to": end, "by_method": by_method, "income_by_category": income, "expense_by_category": expense,
            "totals": {"receipts": receipts, "other_income": other, "income": receipts + other, "expenses": spent, "result": receipts + other - spent},
            "note": ("Только денежные движения за период: поступления по оплатам броней (по дате платежа), прочие доходы и расходы. "
                     "Налоги не считаются. " + ("Общие расходы и доходы без привязки к объекту в выбранный объект не входят." if filtered else ""))}


@api("manager")
def accountant(c: Ctx):
    start, end = _period(c, 31)
    with tx() as conn:
        return _accountant(conn, c, start, end)


def _num(v) -> str:
    return "" if v is None else str(v).replace(".", ",")


@api("manager")
def accountant_csv(c: Ctx):
    start, end = _period(c, 31)
    with tx() as conn:
        d = _accountant(conn, c, start, end)
        pids = _scope(conn, c)
        reg = all_(conn, "SELECT p.paid_on, p.kind, p.method, p.amount, p.note, b.guest_name, b.check_in, b.check_out, r.name AS room_name"
                         " FROM booking_payments p JOIN bookings b ON b.id = p.booking_id JOIN rooms r ON r.id = b.room_id"
                         " WHERE p.account_id = %s AND b.property_id = ANY(%s::uuid[]) AND p.paid_on >= %s AND p.paid_on < %s"
                         " ORDER BY p.paid_on, p.created_at LIMIT 20000", (c.account_id, pids, start, end))
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    shown_to = end - timedelta(days=1)
    w.writerow(["Сводка для бухгалтера", str(start), str(shown_to)])
    w.writerow([])
    w.writerow(["Поступления по оплатам броней"])
    w.writerow(["Способ", "Оплаты", "Возвраты", "Итого"])
    for x in d["by_method"]:
        w.writerow([x["label"], _num(x["payments"]), _num(x["refunds"]), _num(x["net"])])
    w.writerow(["Всего поступлений", "", "", _num(d["totals"]["receipts"])])
    w.writerow([])
    w.writerow(["Прочие доходы по категориям"])
    w.writerow(["Категория", "Записей", "Сумма"])
    for x in d["income_by_category"]:
        w.writerow([csv_safe(x["name"]), x["n"], _num(x["amount"])])
    w.writerow(["Всего прочих доходов", "", _num(d["totals"]["other_income"])])
    w.writerow([])
    w.writerow(["Расходы по категориям"])
    w.writerow(["Категория", "Записей", "Сумма"])
    for x in d["expense_by_category"]:
        w.writerow([csv_safe(x["name"]), x["n"], _num(x["amount"])])
    w.writerow(["Всего расходов", "", _num(d["totals"]["expenses"])])
    w.writerow([])
    w.writerow(["Итого: поступления + прочие доходы − расходы", "", _num(d["totals"]["result"])])
    w.writerow([])
    w.writerow(["Реестр платежей"])
    w.writerow(["Дата", "Вид", "Способ", "Сумма", "Гость", "Номер", "Заезд", "Выезд", "Комментарий"])
    for r in reg:
        w.writerow([r["paid_on"], "Возврат" if r["kind"] == "refund" else "Оплата", METHODS.get(r["method"], r["method"]), _num(r["amount"]),
                    csv_safe(r["guest_name"]), csv_safe(r["room_name"]), r["check_in"], r["check_out"], csv_safe(r["note"])])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=accountant_{start}_{shown_to}.csv"})


# ---------- подсказки для главной ----------

def home_hints(conn, account_id, prop_ids: list[str], today: date, days: int = 14, low_percent: int = 30) -> dict:
    """Что можно улучшить в ближайшие дни: пустые даты (низкая загрузка) и «окна» в одну ночь между бронями номера."""
    rooms = _rooms_count(conn, prop_ids)
    low: list[dict] = []
    if rooms:
        end = today + timedelta(days=days)
        busy = {r["day"]: r["n"] for r in all_(
            conn, "SELECT g::date AS day, count(DISTINCT b.room_id) AS n FROM bookings b JOIN rooms r ON r.id = b.room_id"
                  " CROSS JOIN LATERAL generate_series(greatest(b.check_in, %s::date), least(b.check_out - 1, %s::date), interval '1 day') g"
                  " WHERE b.account_id = %s AND r.property_id = ANY(%s::uuid[]) AND b.status IN ('confirmed', 'pending', 'blocked')"
                  " AND b.check_in < %s AND b.check_out > %s GROUP BY g::date", (today, end - timedelta(days=1), account_id, prop_ids, end, today))}
        for i in range(days):
            day = today + timedelta(days=i)
            occ = round(busy.get(day, 0) * 100 / rooms)
            if occ < low_percent:
                low.append({"date": day, "occupancy": occ})
    gaps = all_(conn, "SELECT r.name AS room_name, a.check_out AS date FROM bookings a JOIN bookings b ON b.room_id = a.room_id AND b.check_in = a.check_out + 1"
                      " JOIN rooms r ON r.id = a.room_id WHERE a.account_id = %s AND r.property_id = ANY(%s::uuid[])"
                      " AND a.status IN ('confirmed', 'pending') AND b.status IN ('confirmed', 'pending') AND a.check_out >= %s"
                      " AND a.check_out < %s AND NOT EXISTS (SELECT 1 FROM bookings x WHERE x.room_id = a.room_id AND x.status = 'blocked'"
                      " AND x.check_in <= a.check_out AND x.check_out > a.check_out) ORDER BY a.check_out, r.name LIMIT 20",
                (account_id, prop_ids, today, today + timedelta(days=45)))
    return {"low_dates": sorted(low, key=lambda x: (x["occupancy"], x["date"]))[:6], "low_total": len(low), "days": days, "gaps": gaps}


routes = [
    Route("/api/analytics/forecast", forecast),
    Route("/api/analytics/pace", pace),
    Route("/api/analytics/lead-time", lead_time),
    Route("/api/analytics/channels", channels),
    Route("/api/analytics/accountant", accountant),
    Route("/api/analytics/accountant.csv", accountant_csv),
]
