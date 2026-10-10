"""Брони, шахматка, цены по датам, статистика."""
import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import psycopg
from starlette.responses import Response
from starlette.routing import Route

from .. import audit, booklog, config, importer, notify
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..pricing import quote
from ..util import csv_safe, opt_str, parse_date, parse_int, parse_money, parse_uuid
from .base import Ctx, api
from .common import selected_property
from .tariffs import get_plan
from .housekeeping import EFFECTIVE_SQL
from .guests import BK_KEY, flags_for, phone_key
from .money import DEPOSIT_STATUSES, METHODS, add_payment
from .reports import SOURCE_LABELS, _booking_metrics, _expenses_total, _overlap_rows, _rooms_count

STATUSES = ("confirmed", "pending", "blocked", "cancelled")
SOURCES = ("manual", "direct", "avito", "yandex", "sutochno", "ostrovok", "other")
BOOKING_COLS = (
    "b.id, b.property_id, b.room_id, b.check_in, b.check_out, b.status, b.source, b.guest_name,"
    " b.guest_phone, b.guest_email, b.guests_count, b.total_price, b.paid_amount, b.notes,"
    " b.discount_amount, b.discount_reason, b.deposit_amount, b.deposit_status, b.rate_plan_id, b.rate_plan_name,"
    " b.group_id, b.feed_id, b.external_uid, b.hold_expires_at, b.created_at, b.updated_at"
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
    """Понятный текст про занятый номер: чем занят, на какие даты, и что можно сделать."""
    room = one(conn, "SELECT name FROM rooms WHERE id = %s", (room_id,))
    label = f"Номер {room['name']}" if room else "Номер"
    row = one(
        conn,
        "SELECT guest_name, check_in, check_out, source, status FROM bookings"
        " WHERE room_id = %s AND status <> 'cancelled' AND check_in < %s AND check_out > %s"
        " AND (%s::uuid IS NULL OR id <> %s::uuid) ORDER BY check_in LIMIT 1",
        (room_id, check_out, check_in, exclude_id, exclude_id),
    )
    if not row:
        return f"{label} уже занят на эти даты"
    who = "закрыт для продажи" if row["status"] == "blocked" else f"занят: {row['guest_name'] or 'бронь без имени'}"
    return (f"{label} {who}, с {row['check_in'].strftime('%d.%m')} по {row['check_out'].strftime('%d.%m')}. "
            "Выберите другой номер или сдвиньте даты.")


def _load_room(conn, account_id: str, room_id) -> dict:
    room = one(conn, "SELECT r.*, rt.base_price, rt.min_stay, rt.capacity FROM rooms r"
                     " JOIN room_types rt ON rt.id = r.room_type_id"
                     " WHERE r.id = %s AND r.account_id = %s", (parse_uuid(room_id, "Номер"), account_id))
    if not room:
        raise ApiError(404, "Номер не найден")
    return room


def _room_type(conn, room: dict) -> dict:
    return one(conn, "SELECT * FROM room_types WHERE id = %s", (room["room_type_id"],))


# Список и карточка отдельной брони — только менеджер/владелец: горничной для её работы хватает
# /api/board и /api/today (те и так открыты всем ролям), а полнотекстовый поиск по гостям
# по всем броням аккаунта выходит за рамки «только шахматка и заезды».
def _booking_filters(c: Ctx) -> tuple[list[str], list]:
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
    return where, params


@api("manager")
def list_bookings(c: Ctx):
    where, params = _booking_filters(c)
    with tx() as conn:
        return all_(
            conn,
            f"SELECT {BOOKING_COLS}, r.name AS room_name, p.name AS property_name FROM bookings b"
            " JOIN rooms r ON r.id = b.room_id JOIN properties p ON p.id = b.property_id"
            f" WHERE {' AND '.join(where)} ORDER BY b.check_in, r.sort_order LIMIT 1000",
            params,
        )


@api("manager")
def export_bookings(c: Ctx):
    """Выгрузка броней за период в CSV (Excel открывает с кириллицей благодаря BOM)."""
    where, params = _booking_filters(c)
    with tx() as conn:
        rows = all_(
            conn,
            f"SELECT {BOOKING_COLS}, r.name AS room_name, p.name AS property_name FROM bookings b"
            " JOIN rooms r ON r.id = b.room_id JOIN properties p ON p.id = b.property_id"
            f" WHERE {' AND '.join(where)} ORDER BY b.check_in, r.sort_order LIMIT 20000",
            params,
        )
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Заезд", "Выезд", "Ночей", "Объект", "Номер", "Гость", "Телефон", "Email", "Гостей", "Источник",
                "Статус", "Стоимость", "Оплачено", "Остаток", "Комментарий"])
    status_label = {"confirmed": "Подтверждена", "pending": "Ждёт оплаты", "blocked": "Даты закрыты",
                    "cancelled": "Отменена"}
    for r in rows:
        total, paid = Decimal(r["total_price"]), Decimal(r["paid_amount"])
        w.writerow([r["check_in"].strftime("%d.%m.%Y"), r["check_out"].strftime("%d.%m.%Y"),
                    (r["check_out"] - r["check_in"]).days, csv_safe(r["property_name"]), csv_safe(r["room_name"]),
                    csv_safe(r["guest_name"]), csv_safe(r["guest_phone"]), csv_safe(r["guest_email"]),
                    r["guests_count"], SOURCE_LABELS.get(r["source"], r["source"]), status_label[r["status"]],
                    str(total).replace(".", ","), str(paid).replace(".", ","),
                    str(max(total - paid, Decimal("0"))).replace(".", ","), csv_safe(r["notes"])])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=bookings.csv"})


@api("manager")
def import_template(c: Ctx):
    return Response("\ufeff" + importer.TEMPLATE, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=bookings_template.csv"})


@api("manager")
def import_bookings(c: Ctx):
    """Импорт броней из CSV в выбранный объект. dry_run=true — только проверка: ничего не сохраняется,
    но результат (сколько создастся и какие строки с ошибками) тот же, что и при настоящем импорте."""
    text = c.data.get("csv")
    if not isinstance(text, str) or not text.strip():
        raise ApiError(422, "Выберите файл с бронями")
    if len(text.encode("utf-8")) > importer.MAX_BYTES:
        raise ApiError(422, "Файл слишком большой (максимум 1,5 МБ)")
    dry_run = bool(c.data.get("dry_run"))
    try:
        fields, items = importer.read_table(text)
    except ValueError as e:
        raise ApiError(422, str(e))
    errors, created = [], 0
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.data.get("property_id"))
        rooms = {r["name"].strip().lower(): r for r in all_(
            conn, "SELECT r.*, rt.base_price, rt.min_stay, rt.capacity FROM rooms r"
                  " JOIN room_types rt ON rt.id = r.room_type_id WHERE r.property_id = %s AND r.account_id = %s",
            (prop["id"], c.account_id))}
        with conn.transaction():
            for item in items:
                n = item["_line"]
                row, err = importer.normalize(item)
                if err:
                    errors.append({"line": n, "error": err})
                    continue
                room = rooms.get(row["room"].lower())
                if not room:
                    errors.append({"line": n, "error": f"номер «{row['room']}» не найден в объекте «{prop['name']}»"})
                    continue
                total = row["total_price"]
                if total == "auto":
                    total = quote(conn, _room_type(conn, room), row["check_in"], row["check_out"]).total
                try:
                    with conn.transaction():
                        b = one(
                            conn,
                            "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status,"
                            " source, guest_name, guest_phone, guest_email, guests_count, total_price, paid_amount,"
                            " notes) VALUES (%s, %s, %s, %s, %s, 'confirmed', %s, %s, %s, %s, %s, %s, %s, %s)"
                            " RETURNING id",
                            (c.account_id, prop["id"], room["id"], row["check_in"], row["check_out"], row["source"],
                             row["guest_name"], row["guest_phone"], row["guest_email"], row["guests_count"], total,
                             row["paid_amount"], row["notes"]))
                except psycopg.errors.ExclusionViolation:
                    errors.append({"line": n, "error": _overlap_info(conn, room["id"], row["check_in"], row["check_out"], None)})
                    continue
                if row["paid_amount"] > 0:
                    add_payment(conn, c.account_id, b["id"], c.p.user_id, row["paid_amount"], "payment", "other", None,
                                "Из файла импорта", log=False)
                booklog.log(conn, c.account_id, b["id"], c.p.user_id, "created", {
                    "summary": f"{row['check_in'].strftime('%d.%m')}–{row['check_out'].strftime('%d.%m')}, номер {room['name']}, импорт из файла",
                    "source": row["source"]})
                created += 1
            if dry_run:
                raise psycopg.Rollback()
        if not dry_run and created:
            audit.record(conn, c.account_id, c.p.user_id, "bookings_imported", f"Импорт броней из файла: загружено {created}, пропущено {len(errors)}")
    return {"dry_run": dry_run, "created": created, "total": len(items), "skipped": len(errors),
            "errors": errors[:200], "columns": fields}


@api("manager")
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
    discount = parse_money(d.get("discount_amount"), "Скидка")
    deposit = parse_money(d.get("deposit_amount"), "Залог")
    deposit_status = d.get("deposit_status") or ("expected" if deposit else "none")
    if deposit_status not in DEPOSIT_STATUSES:
        raise ApiError(422, "Неверный статус залога")
    paid_in = parse_money(d.get("paid_amount"), "Оплачено")
    extra_ids = d.get("extra_room_ids") or []
    if not isinstance(extra_ids, list) or len(extra_ids) > 30:
        raise ApiError(422, "Слишком много номеров в одной брони (максимум 30)")
    guests_n = parse_int(d.get("guests_count"), "Гостей", 1, default=1)
    with tx() as conn:
        room = _load_room(conn, c.account_id, d.get("room_id"))
        plan = get_plan(conn, c.account_id, d.get("rate_plan_id"), room["room_type_id"]) if status != "blocked" else None
        if d.get("total_price") in (None, "") and status != "blocked":
            total = max(quote(conn, _room_type(conn, room), check_in, check_out, guests_n, plan).total - discount, Decimal("0"))
        else:
            total = parse_money(d.get("total_price"), "Стоимость")
        extras = []
        for rid in dict.fromkeys(parse_uuid(x, "Номер") for x in extra_ids):
            if rid == str(room["id"]):
                continue
            r2 = _load_room(conn, c.account_id, rid)
            if r2["property_id"] != room["property_id"]:
                raise ApiError(422, "Все номера группы должны быть в одном объекте")
            extras.append(r2)
        group_id = str(uuid.uuid4()) if extras else None

        def insert(rm, price, plan_row, guests, disc, dep, dep_status):
            try:
                with conn.transaction():
                    return one(
                        conn,
                        "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status,"
                        " source, guest_name, guest_phone, guest_email, guests_count, total_price, paid_amount, notes,"
                        " discount_amount, discount_reason, deposit_amount, deposit_status, rate_plan_id, rate_plan_name,"
                        " group_id)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                        (c.account_id, rm["property_id"], rm["id"], check_in, check_out, status, source,
                         opt_str(d, "guest_name", max_len=200), opt_str(d, "guest_phone", max_len=50),
                         opt_str(d, "guest_email", max_len=200), guests, price,
                         opt_str(d, "notes"), disc, opt_str(d, "discount_reason", max_len=200) if disc else "", dep, dep_status,
                         plan_row["id"] if plan_row else None, plan_row["name"] if plan_row else "", group_id),
                    )
            except psycopg.errors.ExclusionViolation:
                raise ApiError(409, _overlap_info(conn, rm["id"], check_in, check_out, None) + (f" (номер {rm['name']})" if extras else ""),
                               {"code": "overlap"})

        booking = insert(room, total, plan, guests_n, discount, deposit, deposit_status)
        group_rows = [booking]
        for r2 in extras:
            g2 = min(guests_n, r2["capacity"]) if status != "blocked" else 1
            price2 = Decimal("0") if status == "blocked" else quote(conn, _room_type(conn, r2), check_in, check_out, g2, None).total
            group_rows.append(insert(r2, price2, None, g2, Decimal("0"), Decimal("0"), "none"))
        if paid_in > 0:
            add_payment(conn, c.account_id, booking["id"], c.p.user_id, paid_in, "payment",
                        d.get("payment_method") if d.get("payment_method") in METHODS else "cash", None,
                        "Предоплата при создании брони", log=False)
            booking["paid_amount"] = paid_in
        for row, rm in zip(group_rows, [room, *extras]):
            booklog.log(conn, c.account_id, row["id"], c.p.user_id, "created", {
                "summary": f"{check_in.strftime('%d.%m')}–{check_out.strftime('%d.%m')}, номер {rm['name']}"
                           + (f", группа из {len(group_rows)} номеров" if extras else ""),
                "source": source})
        if status != "blocked":
            names = ", ".join(rm["name"] for rm in [room, *extras])
            notify.send(
                conn, c.account_id, "new_booking",
                f"Новая бронь ({SOURCE_LABELS.get(source, source)}): {'номера' if extras else 'номер'} {names}, "
                f"{check_in.strftime('%d.%m')}–{check_out.strftime('%d.%m')}"
                + (f", {booking['guest_name']}" if booking["guest_name"] else "") + ".",
            )
        booking["group_ids"] = [r["id"] for r in group_rows] if extras else []
        return booking


@api("manager")
def update_booking(c: Ctx):
    bid = parse_uuid(c.path["id"])
    d = c.data
    with tx() as conn:
        b = one(conn, "SELECT * FROM bookings WHERE id = %s AND account_id = %s FOR UPDATE", (bid, c.account_id))
        if not b:
            raise ApiError(404, "Бронь не найдена")
        expected = d.get("expected_updated_at")
        if expected:
            # защита от «двух вкладок»: если бронь успели изменить после того, как её открыли, не затираем чужие правки
            try:
                same = datetime.fromisoformat(str(expected).replace("Z", "+00:00")) == b["updated_at"]
            except ValueError:
                same = True
            if not same:
                raise ApiError(409, "Эту бронь только что изменили в другой вкладке или другой сотрудник. Закройте карточку и откройте заново, чтобы увидеть свежие данные",
                               {"code": "stale"})
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
            elif b["status"] != "pending" and b["source"] == "direct" and config.REQUEST_TTL_HOURS > 0:
                # заявку вернули в ожидание (например, отменили отклонение) — срок ожидания идёт заново
                new["hold_expires_at"] = datetime.now(timezone.utc) + timedelta(hours=config.REQUEST_TTL_HOURS)
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
        if "discount_amount" in d:
            # скидка меняет итог на разницу, если итог не задан вручную в этом же запросе
            new["discount_amount"] = parse_money(d["discount_amount"], "Скидка")
            if "total_price" not in d:
                new["total_price"] = max(Decimal(b["total_price"]) + Decimal(b["discount_amount"]) - new["discount_amount"], Decimal("0"))
        if "discount_reason" in d:
            new["discount_reason"] = opt_str(d, "discount_reason", max_len=200)
        if "deposit_amount" in d:
            new["deposit_amount"] = parse_money(d["deposit_amount"], "Залог")
            if new["deposit_amount"] and b["deposit_status"] == "none" and "deposit_status" not in d:
                new["deposit_status"] = "expected"
        if "deposit_status" in d:
            if d["deposit_status"] not in DEPOSIT_STATUSES:
                raise ApiError(422, "Неверный статус залога")
            new["deposit_status"] = d["deposit_status"]
        paid_delta = Decimal("0")
        if "paid_amount" in d:
            # прежний способ: «Оплачено» — число. Превращаем разницу в запись истории платежей
            target = parse_money(d["paid_amount"], "Оплачено")
            paid_delta = target - Decimal(b["paid_amount"])
            new["paid_amount"] = target
        try:
            with conn.transaction():
                updated = one(
                    conn,
                    "UPDATE bookings SET room_id=%s, check_in=%s, check_out=%s, status=%s, source=%s,"
                    " guest_name=%s, guest_phone=%s, guest_email=%s, guests_count=%s, total_price=%s,"
                    " paid_amount=%s, notes=%s, hold_expires_at=%s, discount_amount=%s, discount_reason=%s,"
                    " deposit_amount=%s, deposit_status=%s, updated_at=now() WHERE id=%s RETURNING *",
                    (new["room_id"], new["check_in"], new["check_out"], new["status"], new["source"],
                     new["guest_name"], new["guest_phone"], new["guest_email"], new["guests_count"],
                     new["total_price"], new["paid_amount"], new["notes"], new["hold_expires_at"],
                     new["discount_amount"], new["discount_reason"], new["deposit_amount"], new["deposit_status"], bid),
                )
        except psycopg.errors.ExclusionViolation:
            raise ApiError(409, _overlap_info(conn, new["room_id"], new["check_in"], new["check_out"], bid),
                           {"code": "overlap"})
        if paid_delta:
            add_payment(conn, c.account_id, bid, c.p.user_id, abs(paid_delta), "payment" if paid_delta > 0 else "refund",
                        "other", None, "Корректировка суммы оплаты", log=False)
        changes = booklog.diff(conn, b, updated)
        if changes:
            cancelled_now = new["status"] == "cancelled" and b["status"] != "cancelled"
            booklog.log(conn, c.account_id, bid, c.p.user_id, "cancelled" if cancelled_now else "updated",
                        {"changes": changes})
        if new["status"] == "cancelled" and b["status"] != "cancelled":
            notify.send(conn, c.account_id, "cancellation",
                            f"Бронь «{updated['guest_name'] or 'без имени'}» отменена "
                            f"({updated['check_in'].strftime('%d.%m')}–{updated['check_out'].strftime('%d.%m')}).")
        return updated


@api("manager")
def delete_booking(c: Ctx):
    """Физически удаляем только ручные закрытия дат; брони гостей отменяются (остаются в истории)."""
    bid = parse_uuid(c.path["id"])
    with tx() as conn:
        b = one(conn, "SELECT status, feed_id, guest_name, check_in, check_out, group_id FROM bookings"
                     " WHERE id = %s AND account_id = %s", (bid, c.account_id))
        if not b:
            raise ApiError(404, "Бронь не найдена")
        if c.q.get("group") and b["group_id"]:
            # отмена всей группы (несколько номеров одного гостя)
            for g in all_(conn, "SELECT id, status, feed_id FROM bookings WHERE group_id = %s AND account_id = %s AND status <> 'cancelled'",
                          (b["group_id"], c.account_id)):
                if g["status"] == "blocked" and not g["feed_id"]:
                    run(conn, "DELETE FROM bookings WHERE id = %s", (g["id"],))
                else:
                    run(conn, "UPDATE bookings SET status = 'cancelled', updated_at = now() WHERE id = %s", (g["id"],))
                    booklog.log(conn, c.account_id, g["id"], c.p.user_id, "cancelled", {"summary": "отмена всей группы"})
            if b["status"] != "blocked":
                notify.send(conn, c.account_id, "cancellation",
                                f"Группа броней «{b['guest_name'] or 'без имени'}» отменена "
                                f"({b['check_in'].strftime('%d.%m')}–{b['check_out'].strftime('%d.%m')}).")
            return
        if b["status"] == "blocked" and not b["feed_id"]:
            run(conn, "DELETE FROM bookings WHERE id = %s", (bid,))
        else:
            run(conn, "UPDATE bookings SET status = 'cancelled', updated_at = now() WHERE id = %s", (bid,))
            if b["status"] != "cancelled":
                booklog.log(conn, c.account_id, bid, c.p.user_id, "cancelled", {})
                notify.send(conn, c.account_id, "cancellation",
                                f"Бронь «{b['guest_name'] or 'без имени'}» отменена "
                                f"({b['check_in'].strftime('%d.%m')}–{b['check_out'].strftime('%d.%m')}).")


@api("manager")
def relocate_booking(c: Ctx):
    """Переселение посреди проживания: бронь делится на две части — до выбранной даты остаётся
    в прежнем номере, с этой даты — в новом. Части связаны в группу, итог делится пропорционально ночам."""
    bid = parse_uuid(c.path["id"])
    d = c.data
    from_date = parse_date(d.get("from_date"), "Дата переселения", "from_date")
    with tx() as conn:
        b = one(conn, "SELECT * FROM bookings WHERE id = %s AND account_id = %s FOR UPDATE", (bid, c.account_id))
        if not b:
            raise ApiError(404, "Бронь не найдена")
        if b["status"] in ("blocked", "cancelled") or b["feed_id"]:
            raise ApiError(422, "Эту бронь переселить нельзя: " + ("она пришла с площадки — переселение делается там" if b["feed_id"] else "она закрыта или отменена"))
        if not b["check_in"] < from_date < b["check_out"]:
            raise ApiError(422, f"Дата переселения должна быть между {b['check_in'].strftime('%d.%m')} и {b['check_out'].strftime('%d.%m')} — не в день заезда и не в день выезда", {"field": "from_date"})
        room = _load_room(conn, c.account_id, d.get("room_id"))
        if room["property_id"] != b["property_id"]:
            raise ApiError(422, "Номер из другого объекта")
        if str(room["id"]) == str(b["room_id"]):
            raise ApiError(422, "Выберите другой номер", {"field": "room_id"})
        n_all, n_first = (b["check_out"] - b["check_in"]).days, (from_date - b["check_in"]).days
        first_total = (Decimal(b["total_price"]) * n_first / n_all).quantize(Decimal("1"))
        second_total = parse_money(d["total_price"], "Стоимость") if d.get("total_price") not in (None, "") else Decimal(b["total_price"]) - first_total
        group_id = b["group_id"] or str(uuid.uuid4())
        # сначала укорачиваем исходную бронь — так освобождается место под вторую часть
        run(conn, "UPDATE bookings SET check_out = %s, total_price = %s, group_id = %s, updated_at = now() WHERE id = %s",
            (from_date, first_total, group_id, bid))
        try:
            with conn.transaction():
                second = one(
                    conn,
                    "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, source, guest_name,"
                    " guest_phone, guest_email, guests_count, total_price, paid_amount, notes, group_id, rate_plan_id, rate_plan_name)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s) RETURNING *",
                    (c.account_id, b["property_id"], room["id"], from_date, b["check_out"], b["status"], b["source"], b["guest_name"],
                     b["guest_phone"], b["guest_email"], b["guests_count"], second_total, b["notes"], group_id, b["rate_plan_id"], b["rate_plan_name"]))
        except psycopg.errors.ExclusionViolation:
            raise ApiError(409, _overlap_info(conn, room["id"], from_date, b["check_out"], None), {"code": "overlap"})
        old_room = one(conn, "SELECT name FROM rooms WHERE id = %s", (b["room_id"],))
        booklog.log(conn, c.account_id, bid, c.p.user_id, "updated", {"summary": f"Переселение с {from_date.strftime('%d.%m')} в номер {room['name']}"})
        booklog.log(conn, c.account_id, second["id"], c.p.user_id, "created", {
            "summary": f"{from_date.strftime('%d.%m')}–{b['check_out'].strftime('%d.%m')}, номер {room['name']}, переселение из {old_room['name']}", "source": b["source"]})
        return {"first": bid, "second": second["id"], "first_total": first_total, "second_total": second_total}


@api("manager")
def group_members(c: Ctx):
    """Остальные брони той же группы (несколько номеров / части переселения)."""
    bid = parse_uuid(c.path["id"])
    with tx() as conn:
        b = one(conn, "SELECT group_id FROM bookings WHERE id = %s AND account_id = %s", (bid, c.account_id))
        if not b:
            raise ApiError(404, "Бронь не найдена")
        if not b["group_id"]:
            return []
        return all_(conn, "SELECT b.id, b.check_in, b.check_out, b.status, b.total_price, b.paid_amount, r.name AS room_name"
                          " FROM bookings b JOIN rooms r ON r.id = b.room_id WHERE b.group_id = %s AND b.account_id = %s"
                          " ORDER BY b.check_in, r.name", (b["group_id"], c.account_id))


@api("manager")
def save_date_note(c: Ctx):
    day = parse_date(c.data.get("day"), "Дата", "day")
    text = opt_str(c.data, "text", max_len=300)
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.data.get("property_id"))
        if not text:
            run(conn, "DELETE FROM date_notes WHERE property_id = %s AND day = %s", (prop["id"], day))
            return {"day": day, "text": ""}
        run(conn, "INSERT INTO date_notes (account_id, property_id, day, text, user_id) VALUES (%s, %s, %s, %s, %s)"
                  " ON CONFLICT (property_id, day) DO UPDATE SET text = EXCLUDED.text, user_id = EXCLUDED.user_id, updated_at = now()",
            (c.account_id, prop["id"], day, text, c.p.user_id))
    return {"day": day, "text": text}


@api("manager")
def booking_history(c: Ctx):
    """Кто и что менял в брони — от новых записей к старым."""
    bid = parse_uuid(c.path["id"])
    with tx() as conn:
        if not one(conn, "SELECT 1 FROM bookings WHERE id = %s AND account_id = %s", (bid, c.account_id)):
            raise ApiError(404, "Бронь не найдена")
        return all_(
            conn,
            "SELECT l.id, l.action, l.details, l.created_at, coalesce(u.name, 'Система') AS user_name"
            " FROM booking_log l LEFT JOIN users u ON u.id = l.user_id"
            " WHERE l.booking_id = %s AND l.account_id = %s ORDER BY l.created_at DESC, l.id LIMIT 100",
            (bid, c.account_id))


@api()
def free_rooms(c: Ctx):
    """Какие номера свободны на даты — для быстрого подбора при звонке гостя."""
    check_in = parse_date(c.q.get("check_in"), "Дата заезда")
    check_out = parse_date(c.q.get("check_out"), "Дата выезда")
    if check_out <= check_in:
        raise ApiError(422, "Дата выезда должна быть позже даты заезда")
    guests = parse_int(c.q.get("guests"), "Гостей", 1, default=1)
    exclude = parse_uuid(c.q["exclude"]) if c.q.get("exclude") else None
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.q.get("property_id"))
        types = all_(conn, "SELECT * FROM room_types WHERE property_id = %s ORDER BY sort_order, name", (prop["id"],))
        out = []
        for t in types:
            q = quote(conn, t, check_in, check_out, guests)
            rooms = all_(conn, "SELECT r.id, r.name FROM rooms r WHERE r.room_type_id = %s AND NOT EXISTS ("
                               " SELECT 1 FROM bookings b WHERE b.room_id = r.id AND b.status <> 'cancelled'"
                               " AND b.check_in < %s AND b.check_out > %s AND (%s::uuid IS NULL OR b.id <> %s::uuid))"
                               " ORDER BY r.sort_order, r.name", (t["id"], check_out, check_in, exclude, exclude))
            out.append({"room_type_id": t["id"], "type": t["name"], "capacity": t["capacity"], "price": q.total, "nights": q.nights,
                        "fits": t["capacity"] >= guests, "closed": bool(q.closed_dates), "min_stay": q.min_stay,
                        "rooms": rooms})
    return {"types": out, "check_in": check_in, "check_out": check_out}


@api()
def quote_booking(c: Ctx):
    check_in = parse_date(c.q.get("check_in"), "Дата заезда")
    check_out = parse_date(c.q.get("check_out"), "Дата выезда")
    if check_out <= check_in:
        raise ApiError(422, "Дата выезда должна быть позже даты заезда")
    exclude = parse_uuid(c.q["exclude"]) if c.q.get("exclude") else None
    with tx() as conn:
        room = _load_room(conn, c.account_id, c.q.get("room_id"))
        plan = get_plan(conn, c.account_id, c.q.get("rate_plan_id"), room["room_type_id"])
        q = quote(conn, _room_type(conn, room), check_in, check_out,
                  parse_int(c.q.get("guests"), "Гостей", 1, default=1), plan)
        taken = one(conn, "SELECT 1 FROM bookings WHERE room_id = %s AND status <> 'cancelled'"
                          " AND check_in < %s AND check_out > %s AND (%s::uuid IS NULL OR id <> %s::uuid)",
                    (room["id"], check_out, check_in, exclude, exclude))
        busy = _overlap_info(conn, room["id"], check_in, check_out, exclude) if taken else None
        gaps = []
        if not taken:
            prev = one(conn, "SELECT check_out FROM bookings WHERE room_id = %s AND status <> 'cancelled' AND check_out <= %s"
                             " AND (%s::uuid IS NULL OR id <> %s::uuid) ORDER BY check_out DESC LIMIT 1", (room["id"], check_in, exclude, exclude))
            nxt = one(conn, "SELECT check_in FROM bookings WHERE room_id = %s AND status <> 'cancelled' AND check_in >= %s"
                            " AND (%s::uuid IS NULL OR id <> %s::uuid) ORDER BY check_in LIMIT 1", (room["id"], check_out, exclude, exclude))
            if prev and (check_in - prev["check_out"]).days == 1:
                gaps.append(f"Перед этой бронью останется свободной одна ночь ({check_in - timedelta(days=1):%d.%m}) — её будет трудно продать")
            if nxt and (nxt["check_in"] - check_out).days == 1:
                gaps.append(f"После этой брони останется свободной одна ночь ({check_out:%d.%m}) — её будет трудно продать")
    return {"total": q.total, "nights": q.nights, "min_stay": q.min_stay,
            "closed_dates": q.closed_dates, "busy": busy, "breakdown": q.breakdown, "gaps": gaps}


# ---------- шахматка ----------

@api()
def board(c: Ctx):
    start, end = _date_range(c, 31)
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.q.get("property_id"))
        data = board_payload(conn, c.account_id, prop, start, end)
    if c.p.role == "housekeeper":
        hide_private(data["bookings"])
        data["guest_flags"] = {}
    return data


def hide_private(rows: list[dict]) -> None:
    """Горничной контакты и деньги гостей не нужны (152-ФЗ: только необходимые данные) — убираем их из ответа."""
    for b in rows:
        for k in ("guest_phone", "guest_email", "discount_reason", "rate_plan_name"):
            if k in b:
                b[k] = ""
        for k in ("total_price", "paid_amount", "discount_amount", "deposit_amount"):
            if k in b:
                b[k] = 0


def board_payload(conn, account_id, prop, start, end, contacts: bool = True) -> dict:
    """Данные шахматки объекта. contacts=False — для собственника: без телефонов, почты и заметок гостей."""
    types = all_(conn, "SELECT id, name, capacity, base_price, min_stay FROM room_types"
                       " WHERE property_id = %s ORDER BY sort_order, name", (prop["id"],))
    rooms = all_(conn, f"SELECT r.id, r.room_type_id, r.name, {EFFECTIVE_SQL} AS hk_status, r.hk_note, r.note FROM rooms r"
                       " WHERE r.property_id = %s ORDER BY r.sort_order, r.name", (prop["id"],))
    rates = all_(conn, "SELECT room_type_id, date, price, min_stay, closed FROM rates"
                       " WHERE account_id = %s AND date >= %s AND date < %s", (account_id, start, end))
    bookings = all_(
        conn,
        f"SELECT {BOOKING_COLS} FROM bookings b WHERE b.property_id = %s AND b.status <> 'cancelled'"
        " AND b.check_in < %s AND b.check_out > %s ORDER BY b.check_in",
        (prop["id"], end, start),
    )
    conflicts = one(conn, "SELECT count(*) AS n FROM sync_conflicts WHERE account_id = %s AND NOT resolved",
                    (account_id,))["n"]
    flags = flags_for(conn, account_id, bookings)
    notes = all_(conn, "SELECT day, text FROM date_notes WHERE property_id = %s AND day >= %s AND day < %s", (prop["id"], start, end))
    rate_map: dict = {}
    for r in rates:
        rate_map.setdefault(str(r["room_type_id"]), {})[r["date"].isoformat()] = {
            "price": r["price"], "min_stay": r["min_stay"], "closed": r["closed"]}
    for t in types:
        t["rooms"] = [r for r in rooms if r["room_type_id"] == t["id"]]
        t["rates"] = rate_map.get(str(t["id"]), {})
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days)]
    if not contacts:
        flags = {}
        for b in bookings:
            parts = (b["guest_name"] or "").split()
            b["guest_name"] = (parts[0] + (f" {parts[1][0]}." if len(parts) > 1 else "")) if parts else ""
            for k in ("guest_phone", "guest_email", "notes", "discount_reason", "rate_plan_name"):
                b[k] = ""
            for k in ("paid_amount", "discount_amount", "deposit_amount"):
                b[k] = 0
    return {"property": prop, "from": start, "to": end, "days": days, "room_types": types,
            "bookings": bookings, "open_conflicts": conflicts if contacts else 0, "guest_flags": flags,
            "date_notes": {n["day"].isoformat(): n["text"] for n in notes}}


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
    if d.get("dates"):
        # произвольный набор дат (выбор в календаре цен)
        if not isinstance(d["dates"], list) or len(d["dates"]) > 400:
            raise ApiError(422, "Слишком много дат (максимум 400)")
        dates = sorted({parse_date(x, "Дата") for x in d["dates"]})
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
    with tx() as conn:
        audit.record(conn, c.account_id, c.p.user_id, "rates_changed", f"Изменены цены или ограничения: {count} {'запись' if count % 10 == 1 and count % 100 != 11 else 'записей'} ({start.strftime('%d.%m')}–{end.strftime('%d.%m.%Y')})")
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
            f"SELECT {BOOKING_COLS}, r.name AS room_name, r.cleaned_on AS room_cleaned_on, p.name AS property_name"
            " FROM bookings b JOIN rooms r ON r.id = b.room_id JOIN properties p ON p.id = b.property_id"
            f" WHERE b.account_id = %s AND b.status IN ('confirmed', 'pending')"
            f" AND b.check_in <= %s AND b.check_out >= %s{prop_filter} ORDER BY r.sort_order",
            (c.account_id, day, day, *prop_params),
        )
        rooms_total = one(
            conn, f"SELECT count(*) AS n FROM rooms r WHERE r.account_id = %s{' AND r.property_id = %s' if prop_id else ''}",
            (c.account_id, *prop_params))["n"]
        blocked_now = one(
            conn, "SELECT count(DISTINCT b.room_id) AS n FROM bookings b WHERE b.account_id = %s AND b.status = 'blocked'"
                  f" AND b.check_in <= %s AND b.check_out > %s{prop_filter}",
            (c.account_id, day, day, *prop_params))["n"]
        summary = None
        if c.q.get("summary") and c.p.role in ("owner", "manager"):
            summary = _home_summary(conn, c.account_id, prop_id, date.today())
    if c.p.role == "housekeeper":
        hide_private(rows)
    arrivals = [r for r in rows if r["check_in"] == day]
    staying = [r for r in rows if r["check_in"] < day < r["check_out"]]
    # ночь «на эту дату» занимают заезжающие сегодня и те, кто уже проживает
    occupied = len(arrivals) + len(staying)
    return {
        "date": day,
        "arrivals": arrivals,
        "departures": [r for r in rows if r["check_out"] == day],
        "staying": staying,
        "rooms_total": rooms_total, "occupied_tonight": occupied, "blocked_rooms": blocked_now,
        "free_tonight": max(rooms_total - occupied - blocked_now, 0),
        "summary": summary,
    }


def _home_summary(conn, account_id, prop_id, today: date) -> dict:
    """Главное за минуту: что требует внимания и сколько заработано в этом месяце (для главной страницы владельца)."""
    prop_ids = [prop_id] if prop_id else [str(r["id"]) for r in all_(conn, "SELECT id FROM properties WHERE account_id = %s", (account_id,))]
    pf = " AND b.property_id = ANY(%s::uuid[])"
    alerts = {
        "requests": one(conn, "SELECT count(*) AS n FROM bookings b WHERE b.account_id = %s AND b.source = 'direct' AND b.status = 'pending'" + pf,
                        (account_id, prop_ids))["n"],
        "conflicts": one(conn, "SELECT count(*) AS n FROM sync_conflicts WHERE account_id = %s AND NOT resolved", (account_id,))["n"],
        "repairs": one(conn, "SELECT count(*) AS n FROM rooms r WHERE r.account_id = %s AND r.hk_status = 'repair' AND r.property_id = ANY(%s::uuid[])",
                       (account_id, prop_ids))["n"],
    }
    debt = one(conn, "SELECT count(*) AS n, coalesce(sum(b.total_price - b.paid_amount), 0) AS amount FROM bookings b"
                     " WHERE b.account_id = %s AND b.status = 'confirmed' AND b.check_in <= %s AND b.check_out >= %s"
                     " AND b.total_price > b.paid_amount" + pf,
               (account_id, today, today - timedelta(days=60), prop_ids))
    alerts["debt_count"], alerts["debt_amount"] = debt["n"], debt["amount"]
    start, end = today.replace(day=1), today + timedelta(days=1)
    total_rooms = _rooms_count(conn, [str(r["id"]) for r in all_(conn, "SELECT id FROM properties WHERE account_id = %s", (account_id,))])
    scope_rooms = _rooms_count(conn, prop_ids)
    m = _booking_metrics(_overlap_rows(conn, account_id, prop_ids, start, end), scope_rooms, (end - start).days)
    expenses = _expenses_total(conn, account_id, prop_ids, scope_rooms, total_rooms, start, end)
    return {"alerts": alerts, "month": {"from": start, "revenue": m["revenue"], "expenses": expenses,
                                        "profit": m["revenue"] - expenses, "occupancy": m["occupancy"], "sold_nights": m["sold_nights"]}}


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
            " WHERE b.account_id = %s AND b.guest_phone <> '' AND " + BK_KEY + " = %s AND b.status <> 'cancelled'"
            " ORDER BY b.check_in DESC LIMIT 200",
            (c.account_id, phone_key(phone)),
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
    Route("/api/bookings/export.csv", export_bookings),
    Route("/api/bookings/import-template.csv", import_template),
    Route("/api/bookings/import", import_bookings, methods=["POST"]),
    Route("/api/bookings/quote", quote_booking),
    Route("/api/bookings/free-rooms", free_rooms),
    Route("/api/bookings/{id}/log", booking_history),
    Route("/api/bookings/{id}/relocate", relocate_booking, methods=["POST"]),
    Route("/api/bookings/{id}/group", group_members),
    Route("/api/date-notes", save_date_note, methods=["PUT"]),
    Route("/api/bookings/{id}", get_booking),
    Route("/api/bookings/{id}", update_booking, methods=["PATCH"]),
    Route("/api/bookings/{id}", delete_booking, methods=["DELETE"]),
    Route("/api/board", board),
    Route("/api/rates", set_rates, methods=["PUT"]),
    Route("/api/today", today),
    Route("/api/guests", guest_history),
]
