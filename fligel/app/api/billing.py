"""Тариф и счета для владельца аккаунта: текущий тариф, лимиты, выставленные счета, печатная форма счёта."""
from starlette.routing import Route

from .. import billing, config
from ..admin import PLAN_LABELS, PLANS
from ..db import all_, one, tx
from ..errors import ApiError
from ..util import parse_uuid
from .base import Ctx, api


def seller() -> dict:
    return {**config.SELLER, "configured": bool(config.SELLER["name"] and config.SELLER["inn"] and config.SELLER["account"])}


@api("owner")
def overview(c: Ctx):
    with tx() as conn:
        info = billing.info(conn, c.account_id)
        invoices = all_(conn, "SELECT id, number, plan, months, amount, status, issued_on, paid_on, period_from, period_to, note FROM invoices"
                              " WHERE account_id = %s ORDER BY issued_on DESC, created_at DESC LIMIT 50", (c.account_id,))
    plans = [{"key": k, "label": PLAN_LABELS[k], "limit": PLANS[k], "price": config.PLAN_PRICES[k]} for k in billing.PAID_PLANS]
    return {**info, "invoices": invoices, "plans": plans, "contact": config.SELLER["email"] or "", "seller": seller()}


@api("owner")
def request_invoice(c: Ctx):
    """Клиент просит счёт: оператору сообщение в журнал, сам счёт выставляет человек (платёжного провайдера нет)."""
    plan = c.data.get("plan")
    months = int(c.data.get("months") or 1)
    if plan not in billing.PAID_PLANS:
        raise ApiError(422, "Выберите тариф")
    if not 1 <= months <= 12:
        raise ApiError(422, "Срок — от 1 до 12 месяцев")
    with tx() as conn:
        if one(conn, "SELECT is_demo FROM accounts WHERE id = %s", (c.account_id,))["is_demo"]:
            raise ApiError(403, "В демо-версии счета не выставляются")
        open_ = one(conn, "SELECT 1 FROM invoices WHERE account_id = %s AND status = 'issued'", (c.account_id,))
        if open_:
            raise ApiError(409, "У вас уже есть неоплаченный счёт — оплатите его или напишите нам, чтобы заменить")
        inv = billing.issue_invoice(conn, c.account_id, plan, months, note="Запрошен клиентом")
    return {"id": inv["id"], "number": inv["number"], "amount": inv["amount"]}


@api("owner")
def invoice_print(c: Ctx):
    with tx() as conn:
        inv = one(conn, "SELECT i.*, a.name AS account_name FROM invoices i JOIN accounts a ON a.id = i.account_id WHERE i.id = %s AND i.account_id = %s",
                  (parse_uuid(c.path["id"], "Счёт"), c.account_id))
    if not inv:
        raise ApiError(404, "Счёт не найден")
    return {**inv, "plan_label": PLAN_LABELS.get(inv["plan"], inv["plan"]), "seller": seller()}


routes = [
    Route("/api/billing", overview),
    Route("/api/billing/invoices", request_invoice, methods=["POST"]),
    Route("/api/billing/invoices/{id}", invoice_print),
]
