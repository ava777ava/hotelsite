"""Публичный API v1 для клиентов: объекты, номера, брони, цены. Документация — /api/docs.
Права: ключ read — только чтение; write — ещё создание/изменение броней и цен."""
from starlette.routing import Route

from ..db import all_, one, tx
from ..errors import ApiError
from ..util import parse_date, parse_uuid
from .base import Ctx, v1
from .bookings import create_booking, set_rates, update_booking

BOOKING_FIELDS = ("id, property_id, room_id, check_in, check_out, status, source, guest_name, guest_phone, guest_email, guests_count,"
                  " total_price, paid_amount, notes, created_at, updated_at")
CREATE_KEYS = ("room_id", "check_in", "check_out", "guest_name", "guest_phone", "guest_email", "guests_count", "total_price", "notes", "status", "paid_amount")
UPDATE_KEYS = ("check_in", "check_out", "room_id", "guest_name", "guest_phone", "guest_email", "guests_count", "total_price", "notes", "status", "expected_updated_at")


def _only(data: dict, keys) -> dict:
    return {k: data[k] for k in keys if k in data}


@v1()
def properties(c: Ctx):
    with tx() as conn:
        return {"items": all_(conn, "SELECT id, name, address, phone, check_in_time, check_out_time FROM properties WHERE account_id = %s ORDER BY created_at", (c.account_id,))}


@v1()
def rooms(c: Ctx):
    with tx() as conn:
        where, params = ["r.account_id = %s"], [c.account_id]
        if c.q.get("property_id"):
            where.append("r.property_id = %s")
            params.append(parse_uuid(c.q["property_id"], "Объект"))
        return {"items": all_(conn, "SELECT r.id, r.name, r.property_id, r.room_type_id, rt.name AS room_type, rt.capacity, rt.base_price FROM rooms r"
                                    " JOIN room_types rt ON rt.id = r.room_type_id WHERE " + " AND ".join(where) + " ORDER BY r.property_id, r.sort_order, r.name", params)}


@v1()
def bookings_list(c: Ctx):
    start = parse_date(c.q.get("from"), "from") if c.q.get("from") else None
    end = parse_date(c.q.get("to"), "to") if c.q.get("to") else None
    if not (start and end):
        raise ApiError(422, "Укажите период: from=ГГГГ-ММ-ДД&to=ГГГГ-ММ-ДД")
    if (end - start).days > 400:
        raise ApiError(422, "Период не больше 400 дней")
    where = ["account_id = %s", "status <> 'blocked'", "check_in < %s", "check_out > %s"]
    params: list = [c.account_id, end, start]
    if c.q.get("property_id"):
        where.append("property_id = %s"); params.append(parse_uuid(c.q["property_id"], "Объект"))
    if c.q.get("status"):
        if c.q["status"] not in ("confirmed", "pending", "cancelled"):
            raise ApiError(422, "status: confirmed, pending или cancelled")
        where.append("status = %s"); params.append(c.q["status"])
    with tx() as conn:
        return {"items": all_(conn, f"SELECT {BOOKING_FIELDS} FROM bookings WHERE {' AND '.join(where)} ORDER BY check_in, created_at LIMIT 1000", params)}


@v1()
def booking_get(c: Ctx):
    with tx() as conn:
        b = one(conn, f"SELECT {BOOKING_FIELDS} FROM bookings WHERE id = %s AND account_id = %s AND status <> 'blocked'", (parse_uuid(c.path["id"], "Бронь"), c.account_id))
    if not b:
        raise ApiError(404, "Бронь не найдена")
    return b


@v1("write")
def booking_create(c: Ctx):
    data = _only(c.data, CREATE_KEYS)
    if data.get("status") not in (None, "confirmed", "pending"):
        raise ApiError(422, "status: confirmed или pending")
    data["source"] = "other"
    c.data = data
    r = create_booking.fn(c)
    return {k: r[k] for k in BOOKING_FIELDS.replace(" ", "").split(",")}


@v1("write")
def booking_update(c: Ctx):
    data = _only(c.data, UPDATE_KEYS)
    if not data:
        raise ApiError(422, "Нечего менять")
    c.data = data
    r = update_booking.fn(c)
    return {k: r[k] for k in BOOKING_FIELDS.replace(" ", "").split(",")}


@v1()
def room_types(c: Ctx):
    with tx() as conn:
        return {"items": all_(conn, "SELECT id, property_id, name, capacity, base_price, min_stay FROM room_types WHERE account_id = %s ORDER BY property_id, sort_order, name", (c.account_id,))}


@v1()
def prices_get(c: Ctx):
    rt = parse_uuid(c.q.get("room_type_id"), "room_type_id")
    start, end = parse_date(c.q.get("from"), "from"), parse_date(c.q.get("to"), "to")
    if end <= start or (end - start).days > 400:
        raise ApiError(422, "Период: to позже from, не больше 400 дней")
    with tx() as conn:
        t = one(conn, "SELECT base_price, min_stay FROM room_types WHERE id = %s AND account_id = %s", (rt, c.account_id))
        if not t:
            raise ApiError(404, "Категория не найдена")
        items = all_(conn, "SELECT g::date AS date, coalesce(r.price, %s) AS price, coalesce(r.min_stay, %s) AS min_stay, coalesce(r.closed, false) AS closed"
                           " FROM generate_series(%s::date, %s::date - 1, interval '1 day') g LEFT JOIN rates r ON r.room_type_id = %s AND r.date = g::date ORDER BY 1",
                     (t["base_price"], t["min_stay"], start, end, rt))
    return {"room_type_id": rt, "items": items}


@v1("write")
def prices_set(c: Ctx):
    data = _only(c.data, ("room_type_id", "date_from", "date_to", "price", "min_stay", "closed", "weekdays"))
    if "room_type_id" not in data:
        raise ApiError(422, "Укажите room_type_id")
    data["room_type_ids"] = [data.pop("room_type_id")]
    c.data = data
    return set_rates.fn(c)


routes = [
    Route("/api/v1/properties", properties),
    Route("/api/v1/rooms", rooms),
    Route("/api/v1/room-types", room_types),
    Route("/api/v1/bookings", bookings_list),
    Route("/api/v1/bookings", booking_create, methods=["POST"]),
    Route("/api/v1/bookings/{id}", booking_get),
    Route("/api/v1/bookings/{id}", booking_update, methods=["PATCH"]),
    Route("/api/v1/prices", prices_get),
    Route("/api/v1/prices", prices_set, methods=["PUT"]),
]
