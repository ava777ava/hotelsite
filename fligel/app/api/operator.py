"""Панель оператора сервиса (вы, а не клиенты): свой вход, список клиентов, тарифы и оплата, заметки — то же, что делает CLI `python -m app.admin`."""
from datetime import timedelta

from starlette.routing import Route

from .. import admin, audit, billing, config, ratelimit
from ..admin import PLAN_LABELS, PLANS
from ..auth import hash_password, make_operator_token, verify_password
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_date, parse_int, parse_money, parse_uuid
from .base import Ctx, op_api


@op_api(public=True)
def login(c: Ctx):
    email = str(c.data.get("email") or "").strip().lower()
    password = str(c.data.get("password") or "")
    ip = c.request.client.host if c.request.client else "unknown"
    if not ratelimit.allow(f"operator-login:{ip}", config.OPERATOR_LOGIN_PER_10MIN, 600):
        raise ApiError(429, "Слишком много попыток входа. Подождите 10 минут")
    with tx() as conn:
        op = one(conn, "SELECT * FROM operators WHERE lower(email) = %s FOR UPDATE", (email,))
        if op and op["locked_until"] and op["locked_until"] > one(conn, "SELECT now() AS n")["n"]:
            raise ApiError(423, "Вход временно заблокирован после нескольких неверных паролей")
        ok = bool(op) and verify_password(password, op["password_hash"])
        if op:
            if ok:
                run(conn, "UPDATE operators SET failed_attempts = 0, locked_until = NULL, last_login_at = now() WHERE id = %s", (op["id"],))
            else:
                bad = op["failed_attempts"] + 1
                run(conn, "UPDATE operators SET failed_attempts = %s, locked_until = CASE WHEN %s >= 5 THEN now() + interval '15 minutes' END WHERE id = %s", (bad, bad, op["id"]))
    if not ok:
        raise ApiError(401, "Неверный email или пароль")
    return {"token": make_operator_token(op["id"]), "name": op["name"] or op["email"]}


def _account_rows(conn) -> list[dict]:
    rows = admin.list_accounts(conn)
    extra = {r["id"]: r for r in all_(conn, "SELECT a.id, a.operator_notes, a.is_demo, a.created_at,"
                                            " (SELECT count(*) FROM invoices i WHERE i.account_id = a.id AND i.status = 'issued') AS open_invoices FROM accounts a")}
    for r in rows:
        e = extra[r["id"]]
        r["notes"] = e["operator_notes"]; r["is_demo"] = e["is_demo"]; r["open_invoices"] = e["open_invoices"]
        r["trial_ends"] = (e["created_at"].date() + timedelta(days=billing.TRIAL_DAYS)) if r["plan"] == "trial" else None
        r["plan_label"] = PLAN_LABELS.get(r["plan"], r["plan"])
    return rows


@op_api()
def accounts(c: Ctx):
    with tx() as conn:
        return {"items": _account_rows(conn), "stats": admin.stats(conn), "plans": [{"key": k, "label": v} for k, v in PLAN_LABELS.items()],
                "prices": config.PLAN_PRICES}


@op_api()
def account_detail(c: Ctx):
    aid = parse_uuid(c.path["id"], "Аккаунт")
    with tx() as conn:
        acc = next((r for r in _account_rows(conn) if str(r["id"]) == aid), None)
        if not acc:
            raise ApiError(404, "Аккаунт не найден")
        users = all_(conn, "SELECT name, email, role, last_login_at FROM users WHERE account_id = %s ORDER BY created_at", (aid,))
        invoices = all_(conn, "SELECT id, number, plan, months, amount, status, issued_on, paid_on, period_to, note FROM invoices WHERE account_id = %s ORDER BY issued_on DESC, created_at DESC", (aid,))
        props = all_(conn, "SELECT p.name, (SELECT count(*) FROM rooms r WHERE r.property_id = p.id) AS rooms FROM properties p WHERE p.account_id = %s ORDER BY p.created_at", (aid,))
    return {"account": acc, "users": users, "invoices": invoices, "properties": props}


@op_api()
def account_update(c: Ctx):
    aid = parse_uuid(c.path["id"], "Аккаунт")
    d = c.data
    with tx() as conn:
        acc = one(conn, "SELECT * FROM accounts WHERE id = %s FOR UPDATE", (aid,))
        if not acc:
            raise ApiError(404, "Аккаунт не найден")
        if "status" in d:
            if d["status"] not in ("active", "suspended"):
                raise ApiError(422, "Статус: active или suspended")
            run(conn, "UPDATE accounts SET status = %s WHERE id = %s", (d["status"], aid))
        if "plan" in d:
            if d["plan"] not in PLANS:
                raise ApiError(422, "Неизвестный тариф")
            run(conn, "UPDATE accounts SET plan = %s WHERE id = %s", (d["plan"], aid))
        if "paid_until" in d:
            run(conn, "UPDATE accounts SET paid_until = %s WHERE id = %s", (parse_date(d["paid_until"], "Оплачен до") if d["paid_until"] else None, aid))
        if "notes" in d:
            run(conn, "UPDATE accounts SET operator_notes = %s WHERE id = %s", (opt_str(d, "notes", max_len=4000), aid))
        if any(k in d for k in ("status", "plan", "paid_until")):
            run(conn, "DELETE FROM billing_notices WHERE account_id = %s", (aid,))
    return {"ok": True}


@op_api()
def invoice_create(c: Ctx):
    aid = parse_uuid(c.path["id"], "Аккаунт")
    plan = c.data.get("plan")
    months = parse_int(c.data.get("months"), "Месяцев", 1, default=1)
    if not 1 <= months <= 36:
        raise ApiError(422, "Срок — от 1 до 36 месяцев")
    amount = parse_money(c.data.get("amount"), "Сумма") if c.data.get("amount") not in (None, "") else None
    with tx() as conn:
        if not one(conn, "SELECT 1 FROM accounts WHERE id = %s", (aid,)):
            raise ApiError(404, "Аккаунт не найден")
        try:
            inv = billing.issue_invoice(conn, aid, plan, months, amount, opt_str(c.data, "note", max_len=300), c.operator_id)
        except ValueError as e:
            raise ApiError(422, str(e))
        audit.notify(conn, aid, "billing", f"Выставлен счёт № {inv['number']} на {inv['amount']:.0f} ₽. Он в разделе «Тариф и счета».", "#/billing")
    return inv


@op_api()
def invoice_paid(c: Ctx):
    with tx() as conn:
        try:
            return billing.mark_paid(conn, parse_uuid(c.path["id"], "Счёт"))
        except LookupError as e:
            raise ApiError(404, str(e))
        except ValueError as e:
            raise ApiError(422, str(e))


@op_api()
def invoice_cancel(c: Ctx):
    with tx() as conn:
        n = run(conn, "UPDATE invoices SET status = 'cancelled' WHERE id = %s AND status = 'issued'", (parse_uuid(c.path["id"], "Счёт"),))
    if not n:
        raise ApiError(422, "Отменить можно только неоплаченный счёт")
    return {"ok": True}


@op_api()
def invoice_view(c: Ctx):
    from .billing import seller
    with tx() as conn:
        inv = one(conn, "SELECT i.*, a.name AS account_name FROM invoices i JOIN accounts a ON a.id = i.account_id WHERE i.id = %s", (parse_uuid(c.path["id"], "Счёт"),))
    if not inv:
        raise ApiError(404, "Счёт не найден")
    return {**inv, "plan_label": PLAN_LABELS.get(inv["plan"], inv["plan"]), "seller": seller()}


@op_api()
def reset_password(c: Ctx):
    email = str(c.data.get("email") or "").strip()
    with tx() as conn:
        try:
            return {"password": admin.reset_password(conn, email)}
        except SystemExit as e:
            raise ApiError(404, str(e))


@op_api()
def reminders_now(c: Ctx):
    return {"sent": billing.run_due()}


routes = [
    Route("/api/operator/login", login, methods=["POST"]),
    Route("/api/operator/accounts", accounts),
    Route("/api/operator/accounts/{id}", account_detail),
    Route("/api/operator/accounts/{id}", account_update, methods=["PATCH"]),
    Route("/api/operator/accounts/{id}/invoices", invoice_create, methods=["POST"]),
    Route("/api/operator/invoices/{id}", invoice_view),
    Route("/api/operator/invoices/{id}/paid", invoice_paid, methods=["POST"]),
    Route("/api/operator/invoices/{id}/cancel", invoice_cancel, methods=["POST"]),
    Route("/api/operator/reset-password", reset_password, methods=["POST"]),
    Route("/api/operator/reminders", reminders_now, methods=["POST"]),
]
