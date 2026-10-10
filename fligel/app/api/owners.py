"""Собственники объектов: роль «Собственник» (только чтение своих объектов) и месячный отчёт
собственнику с комиссией управляющей компании (УК) и суммой к выплате."""
import csv
import io
from datetime import date
from decimal import Decimal

from starlette.responses import Response
from starlette.routing import Route

from .. import audit
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import csv_safe, parse_date, parse_money, parse_uuid
from .base import Ctx, api
from .bookings import _date_range, board_payload
from .reports import PENNY, SOURCE_LABELS, _add_months, _money, _overlap_rows


def allowed_properties(conn, c: Ctx) -> list[dict]:
    """Объекты, которые видит пользователь: собственник — только назначенные ему, владелец и
    администратор — все. Горничной отчёты собственника не показываются."""
    if c.p.role == "housekeeper":
        raise ApiError(403, "Недостаточно прав для этого действия")
    if c.p.role == "landlord":
        return all_(conn, "SELECT p.* FROM properties p JOIN user_properties up ON up.property_id = p.id"
                          " WHERE up.user_id = %s AND p.account_id = %s ORDER BY p.created_at", (c.p.user_id, c.account_id))
    return all_(conn, "SELECT * FROM properties WHERE account_id = %s ORDER BY created_at", (c.account_id,))


def pick_property(conn, c: Ctx, property_id) -> dict:
    props = allowed_properties(conn, c)
    if not props:
        raise ApiError(404, "Вам пока не назначен ни один объект. Попросите владельца сервиса открыть доступ")
    if not property_id:
        return props[0]
    pid = parse_uuid(property_id, "Объект")
    for p in props:
        if str(p["id"]) == pid:
            return p
    raise ApiError(404, "Объект не найден")


def build_report(conn, account_id, prop: dict, start: date, end: date) -> dict:
    """Месяц собственника: выручка по ночам, комиссии площадок, расходы объекта, комиссия УК, к выплате.
    Общие расходы аккаунта (без привязки к объекту) в отчёт собственника не входят."""
    rows = _overlap_rows(conn, account_id, [prop["id"]], start, end)
    rooms_n = one(conn, "SELECT count(*) AS n FROM rooms WHERE property_id = %s", (prop["id"],))["n"]
    days = (end - start).days
    sold = blocked = 0
    revenue = Decimal("0")
    by_source: dict[str, dict] = {}
    for r in rows:
        if r["status"] == "blocked":
            blocked += r["nights_in"]
            continue
        share = _money(Decimal(r["total_price"]) * r["nights_in"] / r["nights"])
        sold += r["nights_in"]
        revenue += share
        s = by_source.setdefault(r["source"], {"source": r["source"], "label": SOURCE_LABELS.get(r["source"], r["source"]),
                                               "bookings": 0, "nights": 0, "revenue": Decimal("0")})
        s["bookings"] += 1; s["nights"] += r["nights_in"]; s["revenue"] += share
    commissions = {r["channel"]: Decimal(r["percent"]) for r in all_(
        conn, "SELECT channel, percent FROM channel_commissions WHERE account_id = %s", (account_id,))}
    platform = Decimal("0")
    for s in by_source.values():
        s["commission"] = _money(s["revenue"] * commissions.get(s["source"], Decimal("0")) / 100)
        platform += s["commission"]
    net = revenue - platform
    expenses = all_(conn, "SELECT cat.name, cat.color, sum(e.amount) AS amount FROM expenses e JOIN expense_categories cat ON cat.id = e.category_id"
                          " WHERE e.account_id = %s AND e.property_id = %s AND e.date >= %s AND e.date < %s"
                          " GROUP BY cat.name, cat.color ORDER BY sum(e.amount) DESC", (account_id, prop["id"], start, end))
    expenses_total = sum((Decimal(e["amount"]) for e in expenses), Decimal("0"))
    incomes_total = Decimal(one(conn, "SELECT coalesce(sum(amount), 0) AS n FROM incomes WHERE account_id = %s AND property_id = %s"
                                      " AND date >= %s AND date < %s", (account_id, prop["id"], start, end))["n"])
    pct = Decimal(prop["mc_commission_percent"])
    base = revenue if prop["mc_commission_base"] == "gross" else net
    mc = _money(base * pct / 100)
    payout = net + incomes_total - expenses_total - mc
    stays = all_(conn, "SELECT b.guest_name, b.check_in, b.check_out, b.source, b.total_price, r.name AS room_name,"
                       " (least(b.check_out, %s::date) - greatest(b.check_in, %s::date)) AS nights_in, (b.check_out - b.check_in) AS nights"
                       " FROM bookings b JOIN rooms r ON r.id = b.room_id WHERE b.account_id = %s AND b.property_id = %s"
                       " AND b.status IN ('confirmed', 'pending') AND b.check_in < %s AND b.check_out > %s ORDER BY b.check_in, r.name",
                 (end, start, account_id, prop["id"], end, start))
    for x in stays:
        parts = (x["guest_name"] or "").split()
        x["guest"] = (parts[0] + (f" {parts[1][0]}." if len(parts) > 1 else "")) if parts else "—"
        x["revenue"] = _money(Decimal(x["total_price"]) * x["nights_in"] / x["nights"])
        x.pop("guest_name"); x.pop("total_price")
    avail = rooms_n * days
    return {
        "property": {"id": prop["id"], "name": prop["name"], "address": prop["address"]},
        "from": start, "to": end, "days": days, "rooms": rooms_n,
        "sold_nights": sold, "blocked_nights": blocked, "occupancy": round(sold * 100 / avail, 1) if avail else 0.0,
        "adr": _money(revenue / sold) if sold else Decimal("0"),
        "revenue": revenue, "platform_commission": platform, "net_revenue": net, "other_incomes": incomes_total,
        "expenses": expenses, "expenses_total": expenses_total,
        "mc_percent": pct, "mc_base": prop["mc_commission_base"], "mc_commission": mc, "payout": payout,
        "by_source": sorted(by_source.values(), key=lambda s: -s["revenue"]), "stays": stays,
    }


def _month(c: Ctx) -> tuple[date, date]:
    raw = c.q.get("month")
    if raw:
        start = parse_date(raw + "-01" if len(raw) == 7 else raw, "Месяц").replace(day=1)
    else:
        start = _add_months(date.today().replace(day=1), -1)  # по умолчанию — прошлый, уже закрытый месяц
    return start, _add_months(start, 1)


@api("landlord")
def my_properties(c: Ctx):
    with tx() as conn:
        return [{"id": p["id"], "name": p["name"], "address": p["address"]} for p in allowed_properties(conn, c)]


@api("landlord")
def report(c: Ctx):
    start, end = _month(c)
    with tx() as conn:
        prop = pick_property(conn, c, c.q.get("property_id"))
        data = build_report(conn, c.account_id, prop, start, end)
    if c.q.get("format") == "csv":
        buf = io.StringIO()
        buf.write("﻿")
        w = csv.writer(buf, delimiter=";")
        num = lambda v: str(Decimal(v).quantize(PENNY)).replace(".", ",")
        w.writerow([f"Отчёт собственнику: {csv_safe(data['property']['name'])}", start.strftime("%m.%Y")])
        for label, key in (("Выручка", "revenue"), ("Комиссии площадок", "platform_commission"), ("Чистая выручка", "net_revenue"),
                           ("Прочие доходы", "other_incomes"), ("Расходы объекта", "expenses_total"),
                           (f"Комиссия УК {data['mc_percent']}%", "mc_commission"), ("К выплате собственнику", "payout")):
            w.writerow([label, num(data[key])])
        w.writerow([])
        w.writerow(["Заезд", "Выезд", "Номер", "Гость", "Источник", "Ночей в месяце", "Выручка за месяц"])
        for x in data["stays"]:
            w.writerow([x["check_in"].strftime("%d.%m.%Y"), x["check_out"].strftime("%d.%m.%Y"), csv_safe(x["room_name"]), csv_safe(x["guest"]),
                        SOURCE_LABELS.get(x["source"], x["source"]), x["nights_in"], num(x["revenue"])])
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename=owner_report_{start.strftime('%Y-%m')}.csv"})
    return data


@api("landlord")
def landlord_board(c: Ctx):
    """Шахматка только для чтения — без телефонов, почты и заметок о гостях."""
    start, end = _date_range(c, 31)
    with tx() as conn:
        prop = pick_property(conn, c, c.q.get("property_id"))
        data = board_payload(conn, c.account_id, prop, start, end, contacts=(c.p.role != "landlord"))
    if c.p.role == "landlord":
        for t in data["room_types"]:
            for r in t["rooms"]:
                r["note"] = ""; r["hk_note"] = ""
    return data


@api("owner")
def set_commission(c: Ctx):
    """Комиссия управляющей компании по объекту (процент и от какой суммы считается)."""
    pct = parse_money(c.data.get("percent"), "Комиссия УК")
    if pct > 100:
        raise ApiError(422, "Комиссия не может быть больше 100%")
    base = c.data.get("base") or "net"
    if base not in ("gross", "net"):
        raise ApiError(422, "База комиссии: выручка или чистая выручка")
    with tx() as conn:
        if not run(conn, "UPDATE properties SET mc_commission_percent = %s, mc_commission_base = %s WHERE id = %s AND account_id = %s",
                   (pct, base, parse_uuid(c.path["id"], "Объект"), c.account_id)):
            raise ApiError(404, "Объект не найден")
        audit.record(conn, c.account_id, c.p.user_id, "commission_changed", f"Комиссия УК по объекту: {pct}% ({'от выручки' if base == 'gross' else 'от чистой выручки'})")
    return {"percent": pct, "base": base}


@api("owner")
def set_user_properties(c: Ctx):
    """Какие объекты видит собственник."""
    uid = parse_uuid(c.path["id"], "Сотрудник")
    ids = c.data.get("property_ids")
    if not isinstance(ids, list):
        raise ApiError(422, "Выберите объекты")
    ids = list(dict.fromkeys(parse_uuid(i, "Объект") for i in ids))
    with tx() as conn:
        u = one(conn, "SELECT role FROM users WHERE id = %s AND account_id = %s", (uid, c.account_id))
        if not u:
            raise ApiError(404, "Сотрудник не найден")
        if u["role"] != "landlord":
            raise ApiError(422, "Доступ к объектам настраивается только для собственников")
        assign_properties(conn, c.account_id, uid, ids)
    return {"property_ids": ids}


def assign_properties(conn, account_id, user_id, property_ids: list[str]) -> None:
    owned = {str(r["id"]) for r in all_(conn, "SELECT id FROM properties WHERE account_id = %s AND id = ANY(%s::uuid[])", (account_id, property_ids))}
    if len(owned) != len(property_ids):
        raise ApiError(404, "Объект не найден")
    run(conn, "DELETE FROM user_properties WHERE user_id = %s", (user_id,))
    for pid in property_ids:
        run(conn, "INSERT INTO user_properties (account_id, user_id, property_id) VALUES (%s, %s, %s)", (account_id, user_id, pid))


routes = [
    Route("/api/landlord/properties", my_properties),
    Route("/api/landlord/report", report),
    Route("/api/landlord/board", landlord_board),
    Route("/api/properties/{id}/commission", set_commission, methods=["PUT"]),
    Route("/api/users/{id}/properties", set_user_properties, methods=["PUT"]),
]
