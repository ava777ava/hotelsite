"""Деньги в брони: платежи и возвраты, дополнительные услуги, справочник услуг."""
from datetime import date
from decimal import Decimal

from starlette.routing import Route

from .. import booklog
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_date, parse_int, parse_money, parse_uuid, req_str
from .base import Ctx, api

METHODS = {"cash": "Наличные", "card": "Карта", "transfer": "Перевод", "online": "Онлайн", "other": "Другое"}
DEPOSIT_STATUSES = ("none", "expected", "held", "returned", "kept")


def _rub(v) -> str:
    return f"{Decimal(v):,.0f}".replace(",", " ") + " ₽"


def _booking(conn, account_id: str, booking_id) -> dict:
    b = one(conn, "SELECT * FROM bookings WHERE id = %s AND account_id = %s FOR UPDATE",
            (parse_uuid(booking_id, "Бронь"), account_id))
    if not b:
        raise ApiError(404, "Бронь не найдена")
    return b


def sync_paid(conn, booking_id) -> Decimal:
    """Пересчитывает bookings.paid_amount по истории платежей."""
    row = one(conn, "SELECT coalesce(sum(CASE WHEN kind = 'payment' THEN amount ELSE -amount END), 0) AS s"
                    " FROM booking_payments WHERE booking_id = %s", (booking_id,))
    run(conn, "UPDATE bookings SET paid_amount = %s, updated_at = now() WHERE id = %s", (row["s"], booking_id))
    return row["s"]


def add_payment(conn, account_id, booking_id, user_id, amount: Decimal, kind="payment", method="cash",
                paid_on: date | None = None, note="", log=True) -> dict:
    p = one(conn, "INSERT INTO booking_payments (account_id, booking_id, user_id, kind, amount, method, paid_on, note)"
                  " VALUES (%s, %s, %s, %s, %s, %s, coalesce(%s, current_date), %s) RETURNING *",
            (account_id, booking_id, user_id, kind, amount, method, paid_on, note))
    sync_paid(conn, booking_id)
    if log:
        booklog.log(conn, account_id, booking_id, user_id, "payment", {
            "summary": f"{'Возврат' if kind == 'refund' else 'Оплата'} {_rub(amount)} ({METHODS[method].lower()})"
                       + (f": {note}" if note else "")})
    return p


def money_state(conn, account_id, booking_id) -> dict:
    b = one(conn, "SELECT id, total_price, paid_amount, discount_amount, discount_reason, deposit_amount,"
                  " deposit_status, updated_at FROM bookings WHERE id = %s AND account_id = %s", (booking_id, account_id))
    if not b:
        raise ApiError(404, "Бронь не найдена")
    payments = all_(conn, "SELECT p.id, p.kind, p.amount, p.method, p.paid_on, p.note, p.created_at,"
                          " coalesce(u.name, '') AS user_name FROM booking_payments p"
                          " LEFT JOIN users u ON u.id = p.user_id WHERE p.booking_id = %s AND p.account_id = %s"
                          " ORDER BY p.paid_on, p.created_at", (booking_id, account_id))
    services = all_(conn, "SELECT id, service_id, name, price, qty FROM booking_services"
                          " WHERE booking_id = %s AND account_id = %s ORDER BY created_at", (booking_id, account_id))
    services_sum = sum((Decimal(s["price"]) * s["qty"] for s in services), Decimal("0"))
    total, paid = Decimal(b["total_price"]), Decimal(b["paid_amount"])
    return {"payments": payments, "services": services, "services_sum": services_sum, "updated_at": b["updated_at"],
            "discount_amount": b["discount_amount"], "discount_reason": b["discount_reason"],
            "deposit_amount": b["deposit_amount"], "deposit_status": b["deposit_status"],
            "stay_price": total + Decimal(b["discount_amount"]) - services_sum,
            "total": total, "paid": paid, "due": max(total - paid, Decimal("0"))}


@api("manager")
def get_money(c: Ctx):
    with tx() as conn:
        return money_state(conn, c.account_id, parse_uuid(c.path["id"], "Бронь"))


@api("manager")
def create_payment(c: Ctx):
    d = c.data
    amount = parse_money(d.get("amount"), "Сумма")
    if amount <= 0:
        raise ApiError(422, "Введите сумму больше нуля", {"field": "amount"})
    kind = d.get("kind") or "payment"
    if kind not in ("payment", "refund"):
        raise ApiError(422, "Неверный тип платежа")
    method = d.get("method") or "cash"
    if method not in METHODS:
        raise ApiError(422, "Неверный способ оплаты")
    paid_on = parse_date(d["paid_on"], "Дата платежа", "paid_on") if d.get("paid_on") else None
    with tx() as conn:
        b = _booking(conn, c.account_id, c.path["id"])
        if b["status"] == "blocked":
            raise ApiError(422, "Для закрытых дат платежи не ведутся")
        if kind == "refund" and amount > Decimal(b["paid_amount"]):
            raise ApiError(422, f"Возвращать больше, чем оплачено ({_rub(b['paid_amount'])}), нельзя", {"field": "amount"})
        add_payment(conn, c.account_id, b["id"], c.p.user_id, amount, kind, method, paid_on, opt_str(d, "note", max_len=300))
        return money_state(conn, c.account_id, b["id"])


@api("manager")
def delete_payment(c: Ctx):
    pid = parse_uuid(c.path["id"], "Платёж")
    with tx() as conn:
        p = one(conn, "SELECT * FROM booking_payments WHERE id = %s AND account_id = %s", (pid, c.account_id))
        if not p:
            raise ApiError(404, "Платёж не найден")
        b = _booking(conn, c.account_id, p["booking_id"])
        if p["kind"] == "payment" and Decimal(b["paid_amount"]) - Decimal(p["amount"]) < 0:
            raise ApiError(422, "Сначала удалите возврат, который относится к этому платежу")
        run(conn, "DELETE FROM booking_payments WHERE id = %s", (pid,))
        sync_paid(conn, b["id"])
        booklog.log(conn, c.account_id, b["id"], c.p.user_id, "payment", {
            "summary": f"Удалена запись: {'возврат' if p['kind'] == 'refund' else 'оплата'} {_rub(p['amount'])}"})
        return money_state(conn, c.account_id, b["id"])


@api("manager")
def add_service(c: Ctx):
    d = c.data
    qty = parse_int(d.get("qty"), "Количество", 1, default=1)
    if qty > 100:
        raise ApiError(422, "Слишком большое количество")
    with tx() as conn:
        b = _booking(conn, c.account_id, c.path["id"])
        if b["status"] == "blocked":
            raise ApiError(422, "Для закрытых дат услуги не добавляются")
        if d.get("service_id"):
            s = one(conn, "SELECT name, price FROM services WHERE id = %s AND account_id = %s",
                    (parse_uuid(d["service_id"], "Услуга"), c.account_id))
            if not s:
                raise ApiError(404, "Услуга не найдена")
            name, price = s["name"], s["price"]
            if d.get("price") not in (None, ""):
                price = parse_money(d["price"], "Цена")
        else:
            name, price = req_str(d, "name", "Название услуги", 200), parse_money(d.get("price"), "Цена")
        run(conn, "INSERT INTO booking_services (account_id, booking_id, service_id, name, price, qty)"
                  " VALUES (%s, %s, %s, %s, %s, %s)", (c.account_id, b["id"], d.get("service_id") or None, name, price, qty))
        run(conn, "UPDATE bookings SET total_price = total_price + %s, updated_at = now() WHERE id = %s", (price * qty, b["id"]))
        booklog.log(conn, c.account_id, b["id"], c.p.user_id, "updated", {
            "summary": f"Добавлена услуга «{name}»" + (f" × {qty}" if qty > 1 else "") + f" — {_rub(price * qty)}"})
        return money_state(conn, c.account_id, b["id"])


@api("manager")
def remove_service(c: Ctx):
    sid = parse_uuid(c.path["id"], "Услуга")
    with tx() as conn:
        s = one(conn, "SELECT * FROM booking_services WHERE id = %s AND account_id = %s", (sid, c.account_id))
        if not s:
            raise ApiError(404, "Услуга не найдена")
        b = _booking(conn, c.account_id, s["booking_id"])
        run(conn, "DELETE FROM booking_services WHERE id = %s", (sid,))
        run(conn, "UPDATE bookings SET total_price = greatest(total_price - %s, 0), updated_at = now() WHERE id = %s",
            (Decimal(s["price"]) * s["qty"], b["id"]))
        booklog.log(conn, c.account_id, b["id"], c.p.user_id, "updated", {
            "summary": f"Убрана услуга «{s['name']}» — {_rub(Decimal(s['price']) * s['qty'])}"})
        return money_state(conn, c.account_id, b["id"])


# ---------- справочник услуг ----------
@api("manager")
def list_services(c: Ctx):
    with tx() as conn:
        return all_(conn, "SELECT id, name, price, active FROM services WHERE account_id = %s"
                          " ORDER BY sort_order, name", (c.account_id,))


@api("owner")
def create_service(c: Ctx):
    name = req_str(c.data, "name", "Название", 200)
    price = parse_money(c.data.get("price"), "Цена")
    with tx() as conn:
        if one(conn, "SELECT count(*) AS n FROM services WHERE account_id = %s", (c.account_id,))["n"] >= 100:
            raise ApiError(422, "Слишком много услуг в справочнике")
        return one(conn, "INSERT INTO services (account_id, name, price) VALUES (%s, %s, %s)"
                         " RETURNING id, name, price, active", (c.account_id, name, price))


@api("owner")
def update_service(c: Ctx):
    sid = parse_uuid(c.path["id"], "Услуга")
    d = c.data
    with tx() as conn:
        s = one(conn, "SELECT * FROM services WHERE id = %s AND account_id = %s", (sid, c.account_id))
        if not s:
            raise ApiError(404, "Услуга не найдена")
        name = req_str(d, "name", "Название", 200) if "name" in d else s["name"]
        price = parse_money(d["price"], "Цена") if "price" in d else s["price"]
        active = bool(d["active"]) if "active" in d else s["active"]
        return one(conn, "UPDATE services SET name = %s, price = %s, active = %s WHERE id = %s"
                         " RETURNING id, name, price, active", (name, price, active, sid))


@api("owner")
def delete_service(c: Ctx):
    with tx() as conn:
        if not run(conn, "DELETE FROM services WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Услуга"), c.account_id)):
            raise ApiError(404, "Услуга не найдена")
    return {"ok": True}


@api("manager")
def payments_summary(c: Ctx):
    """Поступления за период: по способам оплаты и по дням (для отчёта «Касса»)."""
    start = parse_date(c.q.get("from"), "Начало периода") if c.q.get("from") else date.today().replace(day=1)
    end = parse_date(c.q.get("to"), "Конец периода") if c.q.get("to") else date.today()
    if end < start or (end - start).days > 400:
        raise ApiError(422, "Неверный период (не больше 400 дней)")
    with tx() as conn:
        rows = all_(conn, "SELECT p.method, p.kind, sum(p.amount) AS total, count(*) AS n FROM booking_payments p"
                          " WHERE p.account_id = %s AND p.paid_on BETWEEN %s AND %s GROUP BY p.method, p.kind",
                    (c.account_id, start, end))
        days = all_(conn, "SELECT p.paid_on AS day, sum(CASE WHEN kind = 'payment' THEN amount ELSE -amount END) AS total"
                          " FROM booking_payments p WHERE p.account_id = %s AND p.paid_on BETWEEN %s AND %s"
                          " GROUP BY p.paid_on ORDER BY p.paid_on", (c.account_id, start, end))
    received = sum((Decimal(r["total"]) for r in rows if r["kind"] == "payment"), Decimal("0"))
    refunded = sum((Decimal(r["total"]) for r in rows if r["kind"] == "refund"), Decimal("0"))
    by_method = {}
    for r in rows:
        m = by_method.setdefault(r["method"], {"method": r["method"], "label": METHODS[r["method"]], "received": Decimal("0"), "refunded": Decimal("0")})
        m["received" if r["kind"] == "payment" else "refunded"] += Decimal(r["total"])
    return {"from": start, "to": end, "received": received, "refunded": refunded, "net": received - refunded,
            "by_method": list(by_method.values()), "days": days}


routes = [
    Route("/api/bookings/{id}/money", get_money),
    Route("/api/bookings/{id}/payments", create_payment, methods=["POST"]),
    Route("/api/payments/summary", payments_summary),
    Route("/api/payments/{id}", delete_payment, methods=["DELETE"]),
    Route("/api/bookings/{id}/services", add_service, methods=["POST"]),
    Route("/api/booking-services/{id}", remove_service, methods=["DELETE"]),
    Route("/api/services", list_services),
    Route("/api/services", create_service, methods=["POST"]),
    Route("/api/services/{id}", update_service, methods=["PATCH"]),
    Route("/api/services/{id}", delete_service, methods=["DELETE"]),
]
