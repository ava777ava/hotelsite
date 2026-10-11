"""Тариф, счета и напоминания об оплате. Платёжного провайдера нет: счёт выставляет оператор, оплату отмечает вручную.

Лимиты тарифа «мягкие»: при превышении клиент видит предупреждение, но работа не блокируется."""
from datetime import date, timedelta

from . import audit, config, mail
from .admin import PLAN_LABELS, PLANS
from .db import all_, one, run, tx

TRIAL_DAYS = 14
PAID_PLANS = ("start", "business", "pro")


def recommended_plan(objects: int) -> str:
    for p in PAID_PLANS:
        if objects <= PLANS[p]:
            return p
    return "custom"


def info(conn, account_id) -> dict:
    acc = one(conn, "SELECT id, name, plan, paid_until, created_at, status, is_demo FROM accounts WHERE id = %s", (account_id,))
    today = date.today()
    used = one(conn, "SELECT count(*) AS n FROM properties WHERE account_id = %s", (account_id,))["n"]
    limit = PLANS.get(acc["plan"], PLANS["trial"])
    trial_ends = (acc["created_at"] + timedelta(days=TRIAL_DAYS)).date() if acc["plan"] == "trial" else None
    end = trial_ends or acc["paid_until"]
    days_left = (end - today).days if end else None
    notice = None
    if acc["is_demo"]:
        pass
    elif used > limit:
        rec = recommended_plan(used)
        notice = {"kind": "limit", "level": "warn",
                  "text": f"Объектов: {used}, а тариф «{PLAN_LABELS.get(acc['plan'])}» включает до {limit}. Работа не ограничена, но стоит перейти на «{PLAN_LABELS.get(rec, 'Индивидуальный')}» — раздел «Тариф и счета»."}
    elif acc["plan"] == "trial" and days_left is not None and days_left <= 3:
        notice = {"kind": "trial", "level": "warn" if days_left >= 0 else "bad",
                  "text": (f"Пробный период заканчивается через {days_left} дн." if days_left > 0 else "Пробный период заканчивается сегодня." if days_left == 0 else "Пробный период закончился.")
                          + " Выберите тариф в разделе «Тариф и счета» — данные сохранятся."}
    elif acc["plan"] != "trial" and acc["plan"] != "custom" and days_left is not None and days_left <= 7:
        notice = {"kind": "paid", "level": "warn" if days_left >= 0 else "bad",
                  "text": (f"Оплата заканчивается через {days_left} дн." if days_left > 0 else "Оплата заканчивается сегодня." if days_left == 0 else f"Срок оплаты истёк {-days_left} дн. назад.")
                          + " Продлить можно в разделе «Тариф и счета»."}
    return {"plan": acc["plan"], "plan_label": PLAN_LABELS.get(acc["plan"], acc["plan"]), "paid_until": acc["paid_until"], "trial_ends": trial_ends,
            "days_left": days_left, "objects_used": used, "objects_limit": limit if limit < 10 ** 6 else None, "over_limit": used > limit,
            "price": config.PLAN_PRICES.get(acc["plan"]), "recommended_plan": recommended_plan(used), "notice": notice, "is_demo": acc["is_demo"]}


def issue_invoice(conn, account_id, plan: str, months: int, amount=None, note: str = "", operator_id=None) -> dict:
    if plan not in PAID_PLANS:
        raise ValueError("Счёт выставляется на тариф «Старт», «Бизнес» или «Профи»")
    if amount is None:
        amount = config.PLAN_PRICES[plan] * months
    seq = one(conn, "SELECT nextval('invoice_seq') AS n")["n"]
    number = f"{date.today().year}-{seq:04d}"
    return one(conn, "INSERT INTO invoices (account_id, number, plan, months, amount, note, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
               (account_id, number, plan, months, amount, note[:300], operator_id))


def mark_paid(conn, invoice_id) -> dict:
    inv = one(conn, "SELECT * FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,))
    if not inv:
        raise LookupError("Счёт не найден")
    if inv["status"] == "paid":
        return inv
    if inv["status"] == "cancelled":
        raise ValueError("Счёт отменён — оплату отметить нельзя")
    acc = one(conn, "SELECT paid_until, plan FROM accounts WHERE id = %s FOR UPDATE", (inv["account_id"],))
    start = max(date.today(), acc["paid_until"]) if acc["paid_until"] and acc["plan"] != "trial" else date.today()
    end = one(conn, "SELECT (%s::date + make_interval(months => %s))::date AS d", (start, inv["months"]))["d"]
    run(conn, "UPDATE invoices SET status = 'paid', paid_on = current_date, period_from = %s, period_to = %s WHERE id = %s", (start, end, inv["id"]))
    run(conn, "UPDATE accounts SET plan = %s, paid_until = %s, status = 'active' WHERE id = %s", (inv["plan"], end, inv["account_id"]))
    run(conn, "DELETE FROM billing_notices WHERE account_id = %s", (inv["account_id"],))
    text = f"Оплата по счёту № {inv['number']} получена. Тариф «{PLAN_LABELS[inv['plan']]}» продлён до {end.strftime('%d.%m.%Y')}. Спасибо!"
    audit.notify(conn, inv["account_id"], "billing", text, "#/billing")
    audit.record(conn, inv["account_id"], None, "invoice_paid", text, "invoice", inv["id"])
    return one(conn, "SELECT * FROM invoices WHERE id = %s", (inv["id"],))


def _notice_once(conn, account_id, key: str) -> bool:
    return bool(run(conn, "INSERT INTO billing_notices (account_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (account_id, key)))


def run_due() -> int:
    """Раз в проход планировщика: напоминания владельцу об окончании пробного периода и оплаты (в колокольчик и на почту), каждое — один раз."""
    sent = 0
    today = date.today()
    with tx() as conn:
        rows = all_(conn, "SELECT a.id, a.plan, a.paid_until, a.created_at, (SELECT u.email FROM users u WHERE u.account_id = a.id AND u.role = 'owner' ORDER BY u.created_at LIMIT 1) AS email"
                          " FROM accounts a WHERE a.status = 'active' AND NOT a.is_demo AND a.plan <> 'custom'")
        for a in rows:
            end = (a["created_at"] + timedelta(days=TRIAL_DAYS)).date() if a["plan"] == "trial" else a["paid_until"]
            if not end:
                continue
            left = (end - today).days
            stages = (3, 1, 0) if a["plan"] == "trial" else (7, 3, 1, 0)
            stage = -1 if left < 0 else min((x for x in stages if left <= x), default=None)
            if stage is None:
                continue
            key = f"{'trial' if a['plan'] == 'trial' else 'paid'}:{end.isoformat()}:{stage}"
            if not _notice_once(conn, a["id"], key):
                continue
            if a["plan"] == "trial":
                text = {-1: "Пробный период закончился.", 0: "Пробный период заканчивается сегодня.", 1: "Пробный период заканчивается завтра."}.get(stage, f"Пробный период заканчивается через {left} дн.")
            else:
                text = {-1: f"Срок оплаты истёк {-left} дн. назад.", 0: "Оплата заканчивается сегодня.", 1: "Оплата заканчивается завтра."}.get(stage, f"Оплата заканчивается через {left} дн.")
            text += " Продлить доступ — раздел «Тариф и счета»: выберите тариф, мы выставим счёт. Данные сохраняются."
            audit.notify(conn, a["id"], "billing", text, "#/billing")
            if a["email"]:
                try:
                    mail.send_or_log(a["email"], "Флигель: напоминание о тарифе", text)
                except Exception:  # noqa: BLE001
                    pass
            sent += 1
    return sent
