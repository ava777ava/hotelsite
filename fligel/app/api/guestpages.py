"""Страницы для гостя по секретной ссылке (без входа): анкета перед приездом и отзыв после выезда.
Анкета — только время приезда, число гостей, пожелания и номер машины. Паспортные данные НЕ собираются (152-ФЗ)."""
import re
from datetime import date

from starlette.routing import Route

from .. import guestlinks, notify, ratelimit
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_int, parse_uuid
from .base import Ctx, api

LOW_RATING = 3  # оценка этого значения и ниже считается низкой — владельцу придёт уведомление


def _first_name(name: str) -> str:
    return (name or "").split()[0] if (name or "").strip() else ""


def _limit(c: Ctx, kind: str) -> None:
    ip = c.request.client.host if c.request.client else "unknown"
    if not ratelimit.allow(f"guestpage:{kind}:{ip}", 60, 3600):
        raise ApiError(429, "Слишком много запросов. Попробуйте через несколько минут")


def _form_row(conn, token: str) -> dict:
    row = one(conn, "SELECT f.*, b.check_in, b.check_out, b.status, b.guest_name, b.guests_count AS booked_guests, b.property_id, b.room_id"
                    " FROM booking_forms f JOIN bookings b ON b.id = f.booking_id JOIN accounts a ON a.id = b.account_id"
                    " WHERE f.token = %s AND a.status = 'active'", (token,))
    if not row or row["status"] in ("cancelled", "blocked"):
        raise ApiError(404, "Ссылка недействительна. Возможно, бронь отменена — свяжитесь с гостиницей")
    return row


def _prop(conn, property_id) -> dict:
    return one(conn, "SELECT name, address, phone, check_in_time, check_out_time FROM properties WHERE id = %s", (property_id,))


@api(public=True)
def form_get(c: Ctx):
    _limit(c, "form")
    with tx() as conn:
        f = _form_row(conn, c.path["token"])
        prop = _prop(conn, f["property_id"])
    return {"property": prop, "check_in": f["check_in"], "check_out": f["check_out"], "guest": _first_name(f["guest_name"]),
            "editable": f["check_out"] >= date.today(),
            "answers": {"arrival_time": f["arrival_time"], "guests_count": f["guests_count"] or f["booked_guests"],
                        "wishes": f["wishes"], "car_number": f["car_number"]},
            "filled": f["filled_at"] is not None}


@api(public=True)
def form_post(c: Ctx):
    _limit(c, "form")
    arrival = opt_str(c.data, "arrival_time", max_len=40)
    guests = parse_int(c.data.get("guests_count"), "Число гостей", 1, default=1)
    if guests > 30:
        raise ApiError(422, "Число гостей: слишком много — позвоните в гостиницу", {"field": "guests_count"})
    wishes = opt_str(c.data, "wishes", max_len=1000)
    car = re.sub(r"\s+", " ", opt_str(c.data, "car_number", max_len=20)).upper()
    with tx() as conn:
        f = _form_row(conn, c.path["token"])
        if f["check_out"] < date.today():
            raise ApiError(410, "Проживание уже закончилось — анкету изменить нельзя")
        run(conn, "UPDATE booking_forms SET arrival_time = %s, guests_count = %s, wishes = %s, car_number = %s, filled_at = now()"
                  " WHERE booking_id = %s", (arrival, guests, wishes, car, f["booking_id"]))
        bits = [f"приедет в {arrival}" if arrival else None, f"гостей: {guests}", f"машина {car}" if car else None, "есть пожелания" if wishes else None]
        notify.send(conn, f["account_id"], "automation",
                    f"Гость {f['guest_name'] or 'без имени'} заполнил анкету ({f['check_in'].strftime('%d.%m')}–{f['check_out'].strftime('%d.%m')}): "
                    + ", ".join(b for b in bits if b) + ".", link="#/bookings", bell=True)
    return {"ok": True}


# ---------- отзыв ----------

def _review_row(conn, token: str) -> dict:
    row = one(conn, "SELECT r.*, b.check_in, b.check_out, b.status, b.guest_name FROM reviews r JOIN bookings b ON b.id = r.booking_id"
                    " JOIN accounts a ON a.id = r.account_id WHERE r.token = %s AND a.status = 'active'", (token,))
    if not row or row["status"] in ("cancelled", "blocked"):
        raise ApiError(404, "Ссылка недействительна")
    return row


@api(public=True)
def review_get(c: Ctx):
    _limit(c, "review")
    with tx() as conn:
        r = _review_row(conn, c.path["token"])
        prop = _prop(conn, r["property_id"])
    return {"property": {"name": prop["name"], "phone": prop["phone"]}, "check_in": r["check_in"], "check_out": r["check_out"],
            "guest": _first_name(r["guest_name"]), "rating": r["rating"], "comment": r["comment"],
            "submitted": r["submitted_at"] is not None, "can_review": r["check_in"] <= date.today()}


@api(public=True)
def review_post(c: Ctx):
    _limit(c, "review")
    rating = parse_int(c.data.get("rating"), "Оценка", 1)
    if rating > 5:
        raise ApiError(422, "Оценка — от 1 до 5", {"field": "rating"})
    comment = opt_str(c.data, "comment", max_len=2000)
    with tx() as conn:
        r = _review_row(conn, c.path["token"])
        if r["check_in"] > date.today():
            raise ApiError(422, "Оставить отзыв можно после заезда")
        run(conn, "UPDATE reviews SET rating = %s, comment = %s, submitted_at = now() WHERE id = %s", (rating, comment, r["id"]))
        was_low = r["rating"] is not None and r["rating"] <= LOW_RATING
        if rating <= LOW_RATING and not was_low:
            room = one(conn, "SELECT name FROM rooms WHERE id = %s", (r["room_id"],))
            notify.send(conn, r["account_id"], "review",
                        f"Низкая оценка {rating} из 5 от гостя {r['guest_name'] or 'без имени'}, номер {room['name'] if room else '—'}"
                        + (f": «{comment[:200]}»" if comment else "") + ".", link="#/reviews", bell=True)
    return {"ok": True}


# ---------- для сотрудников ----------

@api("manager")
def booking_form(c: Ctx):
    """Ответы гостя на анкету и отзыв (если есть) — показываются в карточке брони."""
    bid = parse_uuid(c.path["id"], "Бронь")
    with tx() as conn:
        b = one(conn, "SELECT id FROM bookings WHERE id = %s AND account_id = %s", (bid, c.account_id))
        if not b:
            raise ApiError(404, "Бронь не найдена")
        f = one(conn, "SELECT token, arrival_time, guests_count, wishes, car_number, filled_at FROM booking_forms WHERE booking_id = %s", (bid,))
        rv = one(conn, "SELECT token, rating, comment, submitted_at FROM reviews WHERE booking_id = %s", (bid,))
    return {"form": {**f, "url": guestlinks.form_url(f["token"])} if f else None,
            "review": {**rv, "url": guestlinks.review_url(rv["token"])} if rv else None}


@api("manager")
def booking_link(c: Ctx):
    """Ссылка для гостя (создаётся при первом запросе): kind = form | review."""
    kind = c.data.get("kind")
    if kind not in ("form", "review"):
        raise ApiError(422, "Неизвестный тип ссылки")
    bid = parse_uuid(c.path["id"], "Бронь")
    with tx() as conn:
        b = one(conn, "SELECT id, account_id, property_id, room_id, status FROM bookings WHERE id = %s AND account_id = %s", (bid, c.account_id))
        if not b or b["status"] == "blocked":
            raise ApiError(404, "Бронь не найдена")
        url = guestlinks.form_url(guestlinks.ensure_form(conn, c.account_id, bid)) if kind == "form" \
            else guestlinks.review_url(guestlinks.ensure_review(conn, b))
    return {"url": url}


@api("manager")
def reviews_list(c: Ctx):
    """Внутренняя статистика отзывов: по объектам и номерам + последние отзывы. Наружу никуда не публикуются."""
    where, params = ["r.account_id = %s", "r.submitted_at IS NOT NULL"], [c.account_id]
    if c.q.get("property_id"):
        where.append("r.property_id = %s")
        params.append(parse_uuid(c.q.get("property_id"), "Объект"))
    w = " AND ".join(where)
    with tx() as conn:
        overall = one(conn, f"SELECT count(*) AS n, round(avg(rating)::numeric, 2) AS avg,"
                            f" count(*) FILTER (WHERE rating <= {LOW_RATING}) AS low FROM reviews r WHERE {w}", params)
        dist = all_(conn, f"SELECT rating, count(*) AS n FROM reviews r WHERE {w} GROUP BY rating ORDER BY rating", params)
        by_property = all_(conn, f"SELECT p.id, p.name, count(*) AS n, round(avg(r.rating)::numeric, 2) AS avg FROM reviews r"
                                 f" JOIN properties p ON p.id = r.property_id WHERE {w} GROUP BY p.id, p.name ORDER BY avg DESC", params)
        by_room = all_(conn, f"SELECT rm.id, rm.name, p.name AS property_name, count(*) AS n, round(avg(r.rating)::numeric, 2) AS avg"
                             f" FROM reviews r JOIN rooms rm ON rm.id = r.room_id JOIN properties p ON p.id = r.property_id"
                             f" WHERE {w} GROUP BY rm.id, rm.name, p.name ORDER BY avg, rm.name", params)
        items = all_(conn, f"SELECT r.booking_id, r.rating, r.comment, r.submitted_at, b.guest_name, b.check_in, b.check_out,"
                           f" rm.name AS room_name, p.name AS property_name FROM reviews r JOIN bookings b ON b.id = r.booking_id"
                           f" JOIN rooms rm ON rm.id = r.room_id JOIN properties p ON p.id = r.property_id WHERE {w}"
                           f" ORDER BY r.submitted_at DESC LIMIT 100", params)
        # отправлено просьб оставить отзыв, но ответа ещё нет
        waiting = one(conn, "SELECT count(*) AS n FROM reviews WHERE account_id = %s AND submitted_at IS NULL", (c.account_id,))["n"]
    return {"overall": overall, "distribution": dist, "by_property": by_property, "by_room": by_room, "items": items,
            "waiting": waiting, "low_rating": LOW_RATING}


routes = [
    Route("/api/public/form/{token}", form_get),
    Route("/api/public/form/{token}", form_post, methods=["POST"]),
    Route("/api/public/review/{token}", review_get),
    Route("/api/public/review/{token}", review_post, methods=["POST"]),
    Route("/api/bookings/{id}/form", booking_form),
    Route("/api/bookings/{id}/link", booking_link, methods=["POST"]),
    Route("/api/reviews", reviews_list),
]
