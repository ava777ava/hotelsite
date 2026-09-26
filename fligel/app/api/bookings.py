"""Брони, шахматка, цены по датам, статистика."""
from datetime import date, timedelta
from decimal import Decimal

import psycopg
from starlette.routing import Route

from ..db import all_, one, run, tx
from ..errors import ApiError
from ..pricing import quote
from ..util import opt_str, parse_date, parse_int, parse_money, parse_uuid
from .base import Ctx, api
from .common import selected_property

STATUSES = ("confirmed", "pending", "blocked", "cancelled")
SOURCES = ("manual", "direct", "avito", "yandex", "sutochno", "ostrovok", "other")
BOOKING_COLS = (
    "b.id, b.property_id, b.room_id, b.check_in, b.check_out, b.status, b.source, b.guest_name,"
    " b.guest_phone, b.guest_email, b.guests_count, b.total_price, b.paid_amount, b.notes,"
    " b.feed_id, b.external_uid, b.hold_expires_at, b.created_at, b.updated_at"
)


def _date_range(c: Ctx, default_days: int = 31) -> tuple[date, date]:
    start = parse_date(c.q["from"], "Начало периода") if c.q.get("from") else date.today()
    if c.q.get("to"):
        end = parse_date(c.q["to"], "Конец периода")
    else:
        end = start + timedelta(days=parse_int(c.q.get("days"), "Дней", 1, default=default_days))
    if end <= start:
        raise ApiError(422, "Конец периода должен быть позже начала")
    if (end - start).days > 400:
        raise ApiError(422, "Слишком длинный период (максимум 400 дней)")
    return start, end


def _overlap_info(conn, room_id: str, check_in: date, check_out: date, exclude_id: str | None) -> str:
    row = one(
        conn,
        "SELECT guest_name, check_in, check_out, source, status FROM bookings"
        " WHERE room_id = %s AND status <> 'cancelled' AND check_in < %s AND check_out > %s"
        " AND (%s::uuid IS NULL OR id <> %s::uuid) ORDER BY check_in LIMIT 1",
        (room_id, check_out, check_in, exclude_id, exclude_id),
    )
    if not row:
        return "Номер уже занят на эти даты"
    who = "закрыт" if row["status"] == "blocked" else (row["guest_name"] or "бронь без имени")
    return (f"Номер уже занят: {who}, {row['check_in'].strftime('%d.%m')}–"
            f"{row['check_out'].strftime('%d.%m')}")


def _load_room(conn, account_id: str, room_id) -> dict:
    room = one(conn, "SELECT r.*, rt.base_price, rt.min_stay, rt.capacity FROM rooms r"
                     " JOIN room_types rt ON rt.id = r.room_type_id"
                     " WHERE r.id = %s AND r.account_id = %s", (parse_uuid(room_id, "Номер"), account_id))
    if not room:
        raise ApiError(404, "Номер не найден")
    return room


def _room_type(conn, room: dict) -> dict:
    return one(conn, "SELECT * FROM room_types WHERE id = %s", (room["room_type_id"],))


@api()
def list_bookings(c: Ctx):
    start, end = _date_range(c, 60)
    where = ["b.account_id = %s", "b.check_in < %s", "b.check_out > %s"]
    params: list = [c.account_id, end, start]
    if c.q.get("property_id"):
        where.append("b.property_id = %s")
        params.append(parse_uuid(c.q["property_id"]))
    if c.q.get("status") in STATUSES:
        where.append("b.status = %s")
        params.append(c.q["status"])
    elif c.q.get("include_cancelled") != "1":
        where.append("b.status <> 'cancelled'")
    if c.q.get("q"):
        where.append("(b.guest_name ILIKE %s OR b.guest_phone ILIKE %s OR b.guest_email ILIKE %s)")
        like = f"%{c.q['q']}%"
        params += [like, like, like]
    with tx() as conn:
        return all_(
            conn,
            f"SELECT {BOOKING_COLS}, r.name AS room_name, p.name AS property_name FROM bookings b"
            " JOIN rooms r ON r.id = b.room_id JOIN properties p ON p.id = b.property_id"
            f" WHERE {' AND '.join(where)} ORDER BY b.check_in, r.sort_order LIMIT 1000",
            params,
        )


@api()
def get_booking(c: Ctx):
    with tx() as conn:
        row = one(conn, f"SELECT {BOOKING_COLS}, r.name AS room_name FROM bookings b"
                        " JOIN rooms r ON r.id = b.room_id WHERE b.id = %s AND b.account_id = %s",
                  (parse_uuid(c.path["id"]), c.account_id))
    if not row:
        raise ApiError(404, "Бронь не найдена")
    return row


@api("manager")
def create_booking(c: Ctx):
    d = c.data
    check_in = parse_date(d.get("check_in"), "Дата заезда", "check_in")
    check_out = parse_date(d.get("check_out"), "Дата выезда", "check_out")
    if check_out <= check_in:
        raise ApiError(422, "Дата выезда должна быть позже даты заезда", {"field": "check_out"})
    status = d.get("status") or "confirmed"
    if status not in ("confirmed", "pending", "blocked"):
        raise ApiError(422, "Неверный статус")
    source = d.get("source") or "manual"
    if source not in SOURCES:
        raise ApiError(422, "Неверный источник")
    with tx() as conn:
        room = _load_room(conn, c.account_id, d.get("room_id"))
        if d.get("total_price") in (None, "") and status != "blocked":
            total = quote(conn, _room_type(conn, room), check_in, check_out).total
        else:
            total = parse_money(d.get("total_price"), "Стоимость")
        try:
            with conn.transaction():
                return one(
                    conn,
                    "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status,"
                    " source, guest_name, guest_phone, guest_email, guests_count, total_price, paid_amount, notes)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                    (c.account_id, room["property_id"], room["id"], check_in, check_out, status, source,
                     opt_str(d, "guest_name", max_len=200), opt_str(d, "guest_phone", max_len=50),
                     opt_str(d, "guest_email", max_len=200),
                     parse_int(d.get("guests_count"), "Гостей", 1, default=1), total,
                     parse_money(d.get("paid_amount"), "Оплачено"), opt_str(d, "notes")),
                )
        except psycopg.errors.ExclusionViolation:
            raise ApiError(409, _overlap_info(conn, room["id"], check_in, check_out, None), {"code": "overlap"})


@api("manager")
def update_booking(c: Ctx):
    bid = parse_uuid(c.path["id"])
    d = c.data
    with tx() as conn:
        b = one(conn, "SELECT * FROM bookings WHERE id = %s AND account_id = %s FOR UPDATE", (bid, c.account_id))
        if not b:
            raise ApiError(404, "Бронь не найдена")
        new = dict(b)
        moving = any(k in d for k in ("check_in", "check_out", "room_id"))
        if moving and b["feed_id"] and (
            str(d.get("check_in", b["check_in"])) != str(b["check_in"])
            or str(d.get("check_out", b["check_out"])) != str(b["check_out"])
        ):
            raise ApiError(422, "Даты брони с площадки меняются на самой площадке — они придут при синхронизации")
        if "check_in" in d:
            new["check_in"] = parse_date(d["check_in"], "Дата заезда", "check_in")
        if "check_out" in d:
            new["check_out"] = parse_date(d["check_out"], "Дата выезда", "check_out")
        if new["check_out"] <= new["check_in"]:
            raise ApiError(422, "Дата выезда должна быть позже даты заезда", {"field": "check_out"})
        if "room_id" in d and str(d["room_id"]) != str(b["room_id"]):
            room = _load_room(conn, c.account_id, d["room_id"])
            if room["property_id"] != b["property_id"]:
                raise ApiError(422, "Номер из другого объекта")
            if b["feed_id"]:
                feed = one(conn, "SELECT room_id, room_type_id FROM ical_feeds WHERE id = %s", (b["feed_id"],))
                if feed and feed["room_id"]:
                    raise ApiError(422, "Бронь пришла в календарь конкретного номера — переселить её можно только на площадке")
                if feed and feed["room_type_id"] != room["room_type_id"]:
                    raise ApiError(422, "Бронь с площадки можно переселить только в номер той же категории")
            new["room_id"] = room["id"]
        if "status" in d:
            if d["status"] not in STATUSES:
                raise ApiError(422, "Неверный статус")
            new["status"] = d["status"]
            if d["status"] != "pending":
                new["hold_expires_at"] = None
        if "source" in d and not b["feed_id"]:
            if d["source"] not in SOURCES:
                raise ApiError(422, "Неверный источник")
            new["source"] = d["source"]
        for key, limit in (("guest_name", 200), ("guest_phone", 50), ("guest_email", 200), ("notes", 2000)):
            if key in d:
                new[key] = opt_str(d, key, max_len=limit)
        if "guests_count" in d:
            new["guests_count"] = parse_int(d["guests_count"], "Гостей", 1)
        if "total_price" in d:
            new["total_price"] = parse_money(d["total_price"], "Стоимость")
        if "paid_amount" in d:
            new["paid_amount"] = parse_money(d["paid_amount"], "Оплачено")
        try:
            with conn.transaction():
                return one(
                    conn,
                    "UPDATE bookings SET room_id=%s, check_in=%s, check_out=%s, status=%s, source=%s,"
                    " guest_name=%s, guest_phone=%s, guest_email=%s, guests_count=%s, total_price=%s,"
                    " paid_amount=%s, notes=%s, hold_expires_at=%s, updated_at=now() WHERE id=%s RETURNING *",
                    (new["room_id"], new["check_in"], new["check_out"], new["status"], new["source"],
                     new["guest_name"], new["guest_phone"], new["guest_email"], new["guests_count"],
                     new["total_price"], new["paid_amount"], new["notes"], new["hold_expires_at"], bid),
                )
        except psycopg.errors.ExclusionViolation:
            raise ApiError(409, _overlap_info(conn, new["room_id"], new["check_in"], new["check_out"], bid),
                           {"code": "overlap"})


@api("manager")
def delete_booking(c: Ctx):
    """Физически удаляем только ручные закрытия дат; брони гостей отменяются (остаются в истории)."""
    bid = parse_uuid(c.path["id"])
    with tx() as conn:
        b = one(conn, "SELECT status, feed_id FROM bookings WHERE id = %s AND account_id = %s", (bid, c.account_id))
        if not b:
            raise ApiError(404, "Бронь не найдена")
        if b["status"] == "blocked" and not b["feed_id"]:
            run(conn, "DELETE FROM bookings WHERE id = %s", (bid,))
        else:
            run(conn, "UPDATE bookings SET status = 'cancelled', updated_at = now() WHERE id = %s", (bid,))


@api()
def quote_booking(c: Ctx):
    check_in = parse_date(c.q.get("check_in"), "Дата заезда")
    check_out = parse_date(c.q.get("check_out"), "Дата выезда")
    if check_out <= check_in:
        raise ApiError(422, "Дата выезда должна быть позже даты заезда")
    exclude = parse_uuid(c.q["exclude"]) if c.q.get("exclude") else None
    with tx() as conn:
        room = _load_room(conn, c.account_id, c.q.get("room_id"))
        q = quote(conn, _room_type(conn, room), check_in, check_out)
        taken = one(conn, "SELECT 1 FROM bookings WHERE room_id = %s AND status <> 'cancelled'"
                          " AND check_in < %s AND check_out > %s AND (%s::uuid IS NULL OR id <> %s::uuid)",
                    (room["id"], check_out, check_in, exclude, exclude))
        busy = _overlap_info(conn, room["id"], check_in, check_out, exclude) if taken else None
    return {"total": q.total, "nights": q.nights, "min_stay": q.min_stay,
            "closed_dates": q.closed_dates, "busy": busy}


# ---------- шахматка ----------

@api()
def board(c: Ctx):
    start, end = _date_range(c, 31)
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.q.get("property_id"))
        types = all_(conn, "SELECT id, name, capacity, base_price, min_stay FROM room_types"
                           " WHERE property_id = %s ORDER BY sort_order, name", (prop["id"],))
        rooms = all_(conn, "SELECT id, room_type_id, name FROM rooms WHERE property_id = %s"
                           " ORDER BY sort_order, name", (prop["id"],))
        rates = all_(conn, "SELECT room_type_id, date, price, min_stay, closed FROM rates"
                           " WHERE account_id = %s AND date >= %s AND date < %s", (c.account_id, start, end))
        bookings = all_(
            conn,
            f"SELECT {BOOKING_COLS} FROM bookings b WHERE b.property_id = %s AND b.status <> 'cancelled'"
            " AND b.check_in < %s AND b.check_out > %s ORDER BY b.check_in",
            (prop["id"], end, start),
        )
        conflicts = one(conn, "SELECT count(*) AS n FROM sync_conflicts WHERE account_id = %s AND NOT resolved",
                        (c.account_id,))["n"]
    rate_map: dict = {}
    for r in rates:
        rate_map.setdefault(str(r["room_type_id"]), {})[r["date"].isoformat()] = {
            "price": r["price"], "min_stay": r["min_stay"], "closed": r["closed"]}
    for t in types:
        t["rooms"] = [r for r in rooms if r["room_type_id"] == t["id"]]
        t["rates"] = rate_map.get(str(t["id"]), {})
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days)]
    return {"property": prop, "from": start, "to": end, "days": days, "room_types": types,
            "bookings": bookings, "open_conflicts": conflicts}


# ---------- цены ----------

@api("manager")
def set_rates(c: Ctx):
    """Массовое изменение: категории × период × дни недели → цена / мин. срок / закрытие продаж."""
    d = c.data
    ids = d.get("room_type_ids") or []
    if not isinstance(ids, list) or not ids:
        raise ApiError(422, "Выберите хотя бы одну категорию")
    ids = [parse_uuid(i, "Категория") for i in ids]
    start = parse_date(d.get("date_from"), "Начало периода", "date_from")
    end = parse_date(d.get("date_to"), "Конец периода", "date_to")  # включительно
    if end < start:
        raise ApiError(422, "Конец периода раньше начала")
    if (end - start).days > 400:
        raise ApiError(422, "Слишком длинный период (максимум 400 дней)")
    weekdays = d.get("weekdays")
    weekdays = set(int(w) for w in weekdays) if weekdays else set(range(7))
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    dates = [x for x in dates if x.weekday() in weekdays]
    reset = bool(d.get("reset"))
    price = parse_money(d["price"], "Цена") if d.get("price") not in (None, "") else None
    min_stay = parse_int(d["min_stay"], "Минимальный срок", 1) if d.get("min_stay") not in (None, "") else None
    closed = d.get("closed")
    if not reset and price is None and min_stay is None and closed is None:
        raise ApiError(422, "Укажите цену, минимальный срок или закрытие продаж")
    with tx() as conn:
        owned = all_(conn, "SELECT id FROM room_types WHERE account_id = %s AND id = ANY(%s::uuid[])",
                     (c.account_id, ids))
        if len(owned) != len(set(ids)):
            raise ApiError(404, "Категория не найдена")
        if reset:
            n = run(conn, "DELETE FROM rates WHERE room_type_id = ANY(%s::uuid[]) AND date = ANY(%s::date[])",
                    (ids, dates))
            return {"updated": n}
        count = 0
        with conn.cursor() as cur:
            for rt in ids:
                for day in dates:
                    cur.execute(
                        "INSERT INTO rates (account_id, room_type_id, date, price, min_stay, closed)"
                        " VALUES (%s, %s, %s, %s, %s, coalesce(%s, false))"
                        " ON CONFLICT (room_type_id, date) DO UPDATE SET"
                        " price = coalesce(EXCLUDED.price, rates.price),"
                        " min_stay = coalesce(%s, rates.min_stay),"
                        " closed = coalesce(%s, rates.closed)",
                        (c.account_id, rt, day, price, min_stay, closed, min_stay, closed),
                    )
                    count += 1
    return {"updated": count}


# ---------- день ----------

@api()
def today(c: Ctx):
    day = parse_date(c.q["date"], "Дата") if c.q.get("date") else date.today()
    prop_id = parse_uuid(c.q["property_id"], "Объект") if c.q.get("property_id") else None
    with tx() as conn:
        if prop_id:
            selected_property(conn, c.account_id, prop_id)
        prop_filter = " AND b.property_id = %s" if prop_id else ""
        prop_params = (prop_id,) if prop_id else ()
        rows = all_(
            conn,
            f"SELECT {BOOKING_COLS}, r.name AS room_name, p.name AS property_name FROM bookings b"
            " JOIN rooms r ON r.id = b.room_id JOIN properties p ON p.id = b.property_id"
            f" WHERE b.account_id = %s AND b.status IN ('confirmed', 'pending')"
            f" AND b.check_in <= %s AND b.check_out >= %s{prop_filter} ORDER BY r.sort_order",
            (c.account_id, day, day, *prop_params),
        )
    return {
        "date": day,
        "arrivals": [r for r in rows if r["check_in"] == day],
        "departures": [r for r in rows if r["check_out"] == day],
        "staying": [r for r in rows if r["check_in"] < day < r["check_out"]],
    }


# ---------- карточка гостя ----------

@api("manager")
def guest_history(c: Ctx):
    """История проживаний гостя по телефону — по всем объектам аккаунта."""
    phone = (c.q.get("phone") or "").strip()
    if not phone:
        raise ApiError(422, "Укажите телефон гостя")
    with tx() as conn:
        rows = all_(
            conn,
            f"SELECT {BOOKING_COLS}, r.name AS room_name, p.name AS property_name FROM bookings b"
            " JOIN rooms r ON r.id = b.room_id JOIN properties p ON p.id = b.property_id"
            " WHERE b.account_id = %s AND b.guest_phone = %s AND b.status <> 'cancelled'"
            " ORDER BY b.check_in DESC LIMIT 200",
            (c.account_id, phone),
        )
    return {
        "phone": phone,
        "visits": len(rows),
        "returning": len(rows) >= 2,
        "total_spent": sum((r["total_price"] for r in rows), Decimal("0")),
        "total_paid": sum((r["paid_amount"] for r in rows), Decimal("0")),
        "stays": rows,
    }


routes = [
    Route("/api/bookings", list_bookings),
    Route("/api/bookings", create_booking, methods=["POST"]),
    Route("/api/bookings/quote", quote_booking),
    Route("/api/bookings/{id}", get_booking),
    Route("/api/bookings/{id}", update_booking, methods=["PATCH"]),
    Route("/api/bookings/{id}", delete_booking, methods=["DELETE"]),
    Route("/api/board", board),
    Route("/api/rates", set_rates, methods=["PUT"]),
    Route("/api/today", today),
    Route("/api/guests", guest_history),
]
