"""Модуль прямого бронирования: публичная страница объекта, поиск свободных номеров, заявка гостя."""
from datetime import date

import psycopg
from starlette.routing import Route

from ..db import all_, one, tx
from ..errors import ApiError
from ..pricing import quote
from ..util import opt_str, parse_date, parse_int, parse_uuid, req_str
from .base import Ctx, api

MAX_NIGHTS = 60


def _property(conn, slug: str) -> dict:
    prop = one(conn, "SELECT p.* FROM properties p JOIN accounts a ON a.id = p.account_id"
                     " WHERE p.public_slug = %s AND a.status = 'active'", (slug,))
    if not prop or not prop["booking_enabled"]:
        raise ApiError(404, "Страница бронирования не найдена или отключена")
    return prop


def _dates(check_in_raw, check_out_raw) -> tuple[date, date]:
    check_in = parse_date(check_in_raw, "Дата заезда", "check_in")
    check_out = parse_date(check_out_raw, "Дата выезда", "check_out")
    if check_in < date.today():
        raise ApiError(422, "Дата заезда уже прошла", {"field": "check_in"})
    if check_out <= check_in:
        raise ApiError(422, "Дата выезда должна быть позже даты заезда", {"field": "check_out"})
    if (check_out - check_in).days > MAX_NIGHTS:
        raise ApiError(422, f"Онлайн можно забронировать до {MAX_NIGHTS} ночей — для долгого проживания позвоните нам")
    return check_in, check_out


def _free_rooms(conn, room_type_id, check_in: date, check_out: date) -> list[dict]:
    return all_(
        conn,
        "SELECT r.id, r.name FROM rooms r WHERE r.room_type_id = %s AND NOT EXISTS ("
        " SELECT 1 FROM bookings b WHERE b.room_id = r.id AND b.status <> 'cancelled'"
        " AND b.check_in < %s AND b.check_out > %s) ORDER BY r.sort_order, r.name",
        (room_type_id, check_out, check_in),
    )


@api(public=True)
def property_info(c: Ctx):
    with tx() as conn:
        prop = _property(conn, c.path["slug"])
        types = all_(conn, "SELECT id, name, description, capacity, base_price, min_stay FROM room_types"
                           " WHERE property_id = %s ORDER BY sort_order, name", (prop["id"],))
    return {"name": prop["name"], "address": prop["address"], "phone": prop["phone"],
            "check_in_time": prop["check_in_time"].strftime("%H:%M"),
            "check_out_time": prop["check_out_time"].strftime("%H:%M"), "room_types": types}


@api(public=True)
def availability(c: Ctx):
    check_in, check_out = _dates(c.q.get("check_in"), c.q.get("check_out"))
    guests = parse_int(c.q.get("guests"), "Гостей", 1, default=1)
    result = []
    with tx() as conn:
        prop = _property(conn, c.path["slug"])
        types = all_(conn, "SELECT * FROM room_types WHERE property_id = %s ORDER BY sort_order, name",
                     (prop["id"],))
        for t in types:
            q = quote(conn, t, check_in, check_out)
            free = len(_free_rooms(conn, t["id"], check_in, check_out))
            reason = None
            if t["capacity"] < guests:
                reason = f"Вмещает до {t['capacity']} гостей"
            elif q.closed_dates:
                reason = "На эти даты продажи закрыты"
            elif q.nights < q.min_stay:
                reason = f"Минимальный срок проживания — {q.min_stay} ноч."
            elif free == 0:
                reason = "Нет свободных номеров на эти даты"
            result.append({
                "room_type_id": t["id"], "name": t["name"], "description": t["description"],
                "capacity": t["capacity"], "nights": q.nights, "total": q.total,
                "available": reason is None, "free_rooms": free, "reason": reason,
            })
    return {"check_in": check_in, "check_out": check_out, "guests": guests, "options": result}


@api(public=True)
def create_request(c: Ctx):
    d = c.data
    check_in, check_out = _dates(d.get("check_in"), d.get("check_out"))
    guests = parse_int(d.get("guests"), "Гостей", 1, default=1)
    name = req_str(d, "guest_name", "Имя", 200)
    phone = req_str(d, "guest_phone", "Телефон", 50)
    if sum(ch.isdigit() for ch in phone) < 10:
        raise ApiError(422, "Проверьте номер телефона", {"field": "guest_phone"})
    if not d.get("consent"):
        raise ApiError(422, "Нужно согласие на обработку персональных данных", {"field": "consent"})
    rt_id = parse_uuid(d.get("room_type_id"), "Категория номера")
    with tx() as conn:
        prop = _property(conn, c.path["slug"])
        t = one(conn, "SELECT * FROM room_types WHERE id = %s AND property_id = %s", (rt_id, prop["id"]))
        if not t:
            raise ApiError(404, "Категория номера не найдена")
        if t["capacity"] < guests:
            raise ApiError(422, f"Номер вмещает до {t['capacity']} гостей")
        q = quote(conn, t, check_in, check_out)
        if not q.ok:
            raise ApiError(422, "На эти даты номер недоступен для онлайн-бронирования")
        # Пробуем номера по очереди: ограничение в БД не даст занять номер дважды,
        # даже если два гостя бронируют одновременно
        for room in _free_rooms(conn, t["id"], check_in, check_out):
            try:
                with conn.transaction():
                    b = one(
                        conn,
                        "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status,"
                        " source, guest_name, guest_phone, guest_email, guests_count, total_price, notes)"
                        " VALUES (%s, %s, %s, %s, %s, 'pending', 'direct', %s, %s, %s, %s, %s, %s)"
                        " RETURNING id, check_in, check_out, total_price",
                        (prop["account_id"], prop["id"], room["id"], check_in, check_out, name, phone,
                         opt_str(d, "guest_email", max_len=200), guests, q.total,
                         opt_str(d, "comment", max_len=1000)),
                    )
                break
            except psycopg.errors.ExclusionViolation:
                continue
        else:
            raise ApiError(409, "Пока вы оформляли заявку, свободные номера этой категории закончились")
    return {
        "booking_id": b["id"], "reference": str(b["id"])[:8].upper(), "room_type": t["name"],
        "check_in": b["check_in"], "check_out": b["check_out"], "total": b["total_price"],
        "nights": q.nights, "status": "pending",
        "message": "Заявка принята. Мы свяжемся с вами для подтверждения и оплаты.",
    }


routes = [
    Route("/api/public/{slug}", property_info),
    Route("/api/public/{slug}/availability", availability),
    Route("/api/public/{slug}/book", create_request, methods=["POST"]),
]
