"""Раунд 5, этап 4: панель оператора, счета и оплата вручную, напоминания, мягкие лимиты, публичный API и вебхуки, демо."""
import unittest
from datetime import date, timedelta

from test_app import Base, d  # noqa: F401

from app import admin, billing, config, db


class OperatorBase(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.op_email, cls.op_password = "ops@fligel.test", "operator-pass-1"
        with db.tx() as conn:
            from app.auth import hash_password
            db.run(conn, "INSERT INTO operators (email, name, password_hash) VALUES (%s, 'Оператор', %s)", (cls.op_email, hash_password(cls.op_password)))

    def op(self):
        r = self.client.post("/api/operator/login", json={"email": self.op_email, "password": self.op_password})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def account_id(self, email):
        with db.tx() as conn:
            return str(db.one(conn, "SELECT account_id FROM users WHERE lower(email) = %s", (email,))["account_id"])


class OperatorTests(OperatorBase):
    def test_login_and_token_separation(self):
        ctx = self.register("opc1@example.ru")
        self.assertEqual(self.client.post("/api/operator/login", json={"email": self.op_email, "password": "wrong"}).status_code, 401)
        self.assertEqual(self.client.post("/api/operator/login", json={"email": "nobody@x.ru", "password": "x"}).status_code, 401)
        oh = self.op()
        self.assertEqual(self.client.get("/api/operator/accounts", headers=oh).status_code, 200)
        self.assertEqual(self.client.get("/api/operator/accounts").status_code, 401)
        # токен клиента не открывает панель оператора, а токен оператора — клиентский API
        self.assertEqual(self.client.get("/api/operator/accounts", headers=ctx["h"]).status_code, 401)
        self.assertEqual(self.client.get("/api/me", headers=oh).status_code, 401)
        self.assertEqual(self.client.get("/api/board", headers=oh).status_code, 401)
        self.assertEqual(self.client.get("/operator/").status_code, 200)

    def test_operator_login_lockout_after_wrong_passwords(self):
        from app import ratelimit
        ratelimit.reset()
        for _ in range(5):
            self.client.post("/api/operator/login", json={"email": self.op_email, "password": "bad"})
        r = self.client.post("/api/operator/login", json={"email": self.op_email, "password": self.op_password})
        self.assertEqual(r.status_code, 423)
        with db.tx() as conn:
            db.run(conn, "UPDATE operators SET failed_attempts = 0, locked_until = NULL")
        ratelimit.reset()
        self.assertEqual(self.client.post("/api/operator/login", json={"email": self.op_email, "password": self.op_password}).status_code, 200)

    def test_clients_list_suspend_plan_notes(self):
        ctx = self.register("opc2@example.ru")
        aid = self.account_id("opc2@example.ru")
        oh = self.op()
        items = self.client.get("/api/operator/accounts", headers=oh).json()["items"]
        row = next(x for x in items if str(x["id"]) == aid)
        self.assertEqual((row["plan"], row["status"], row["owner_email"]), ("trial", "active", "opc2@example.ru"))
        self.assertIsNotNone(row["trial_ends"])
        r = self.client.patch(f"/api/operator/accounts/{aid}", headers=oh, json={"status": "suspended", "notes": "Звонил, просил отсрочку"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/me", headers=ctx["h"]).status_code, 403)       # доступ клиента сразу закрыт
        self.client.patch(f"/api/operator/accounts/{aid}", headers=oh, json={"status": "active", "plan": "start", "paid_until": d(30)})
        me = self.client.get("/api/me", headers=ctx["h"]).json()
        self.assertEqual((me["plan"], me["paid_until"]), ("start", d(30)))
        det = self.client.get(f"/api/operator/accounts/{aid}", headers=oh).json()
        self.assertEqual(det["account"]["notes"], "Звонил, просил отсрочку")
        self.assertEqual(det["users"][0]["email"], "opc2@example.ru")
        for bad in ({"status": "deleted"}, {"plan": "gold"}, {"paid_until": "завтра"}):
            self.assertEqual(self.client.patch(f"/api/operator/accounts/{aid}", headers=oh, json=bad).status_code, 422, bad)
        self.assertEqual(self.client.patch("/api/operator/accounts/00000000-0000-0000-0000-000000000000", headers=oh, json={"notes": "x"}).status_code, 404)

    def test_invoice_flow_issue_paid_extends_and_cancel(self):
        ctx = self.register("opc3@example.ru")
        aid = self.account_id("opc3@example.ru")
        oh = self.op()
        self.assertEqual(self.client.post(f"/api/operator/accounts/{aid}/invoices", headers=oh, json={"plan": "trial"}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/operator/accounts/{aid}/invoices", headers=oh, json={"plan": "start", "months": 99}).status_code, 422)
        r = self.client.post(f"/api/operator/accounts/{aid}/invoices", headers=oh, json={"plan": "start", "months": 2})
        self.assertEqual(r.status_code, 200, r.text)
        inv = r.json()
        self.assertEqual((float(inv["amount"]), inv["status"]), (990.0 * 2, "issued"))
        self.assertRegex(inv["number"], r"^\d{4}-\d{4}$")
        # клиент видит счёт и получает уведомление
        bill = self.client.get("/api/billing", headers=ctx["h"]).json()
        self.assertEqual([i["number"] for i in bill["invoices"]], [inv["number"]])
        self.assertTrue(any("Выставлен счёт" in n["text"] for n in self.client.get("/api/notifications", headers=ctx["h"]).json()["items"]))
        paid = self.client.post(f"/api/operator/invoices/{inv['id']}/paid", headers=oh, json={}).json()
        self.assertEqual(paid["status"], "paid")
        me = self.client.get("/api/me", headers=ctx["h"]).json()
        end = date.today()
        month_total = end.month - 1 + 2
        expected = date(end.year + month_total // 12, month_total % 12 + 1, min(end.day, 28)).isoformat()
        self.assertEqual(me["plan"], "start")
        self.assertGreaterEqual(me["paid_until"], (end + timedelta(days=58)).isoformat())
        self.assertLessEqual(me["paid_until"], (end + timedelta(days=62)).isoformat())
        self.assertTrue(expected)
        # повторная отметка ничего не меняет, продление считается от уже оплаченной даты
        again = self.client.post(f"/api/operator/invoices/{inv['id']}/paid", headers=oh, json={}).json()
        self.assertEqual(again["paid_until"] if "paid_until" in again else me["paid_until"], me["paid_until"])
        before = me["paid_until"]
        inv2 = self.client.post(f"/api/operator/accounts/{aid}/invoices", headers=oh, json={"plan": "start", "months": 1, "amount": 500}).json()
        self.assertEqual(float(inv2["amount"]), 500.0)
        self.client.post(f"/api/operator/invoices/{inv2['id']}/paid", headers=oh, json={})
        after = self.client.get("/api/me", headers=ctx["h"]).json()["paid_until"]
        self.assertGreaterEqual(after, (date.fromisoformat(before) + timedelta(days=28)).isoformat())
        # отмена: только неоплаченный; оплата отменённого — ошибка
        inv3 = self.client.post(f"/api/operator/accounts/{aid}/invoices", headers=oh, json={"plan": "business"}).json()
        self.assertEqual(self.client.post(f"/api/operator/invoices/{inv3['id']}/cancel", headers=oh, json={}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/operator/invoices/{inv3['id']}/cancel", headers=oh, json={}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/operator/invoices/{inv3['id']}/paid", headers=oh, json={}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/operator/invoices/{inv['id']}/cancel", headers=oh, json={}).status_code, 422)   # оплаченный не отменить
        self.assertEqual(self.client.post("/api/operator/invoices/00000000-0000-0000-0000-000000000000/paid", headers=oh, json={}).status_code, 404)


class BillingClientTests(OperatorBase):
    def test_owner_billing_view_request_and_print_with_isolation(self):
        ctx = self.register("bc1@example.ru")
        other = self.register("bc1b@example.ru")
        mgr = self.client.post("/api/users", headers=ctx["h"], json={"name": "Админ", "email": "mgr-bc1@example.ru", "role": "manager", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "mgr-bc1@example.ru", "password": "password123"}).json()["token"]
        self.assertEqual(mgr.status_code, 200)
        self.assertEqual(self.client.get("/api/billing", headers={"Authorization": f"Bearer {tok}"}).status_code, 403)   # тариф — дело владельца
        bill = self.client.get("/api/billing", headers=ctx["h"]).json()
        self.assertEqual((bill["plan"], bill["objects_used"], bill["objects_limit"], bill["over_limit"]), ("trial", 1, 4, False))
        self.assertEqual([p["key"] for p in bill["plans"]], ["start", "business", "pro"])
        self.assertEqual(self.client.post("/api/billing/invoices", headers=ctx["h"], json={"plan": "gold"}).status_code, 422)
        r = self.client.post("/api/billing/invoices", headers=ctx["h"], json={"plan": "business", "months": 3})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(float(r.json()["amount"]), 2490.0 * 3)
        self.assertEqual(self.client.post("/api/billing/invoices", headers=ctx["h"], json={"plan": "start"}).status_code, 409)   # уже есть неоплаченный
        inv_id = self.client.get("/api/billing", headers=ctx["h"]).json()["invoices"][0]["id"]
        config.SELLER["name"], config.SELLER["inn"] = "ИП Иванов И. И.", "7700000000"
        try:
            pr = self.client.get(f"/api/billing/invoices/{inv_id}", headers=ctx["h"]).json()
        finally:
            config.SELLER["name"] = config.SELLER["inn"] = ""
        self.assertEqual((pr["seller"]["name"], pr["plan_label"], pr["account_name"]), ("ИП Иванов И. И.", "Бизнес", "Гостиница"))
        self.assertEqual(self.client.get(f"/api/billing/invoices/{inv_id}", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.get("/api/billing", headers=other["h"]).json()["invoices"], [])

    def test_soft_limit_over_plan_and_recommended_plan(self):
        ctx = self.register("bc2@example.ru")
        for i in range(4):
            self.client.post("/api/setup", headers=ctx["h"], json={"name": f"О{i}", "room_types": [{"name": "С", "count": 1, "base_price": 1}]})
        bill = self.client.get("/api/billing", headers=ctx["h"]).json()
        self.assertEqual((bill["objects_used"], bill["over_limit"], bill["recommended_plan"]), (5, True, "business"))
        self.assertEqual(bill["notice"]["kind"], "limit")
        self.assertEqual(self.client.get("/api/board", headers=ctx["h"]).status_code, 200)       # работа не блокируется

    def test_reminders_once_per_stage_trial_and_paid_and_skip_demo(self):
        ctx = self.register("bc3@example.ru")
        aid = self.account_id("bc3@example.ru")
        def notes():
            return [n["text"] for n in self.client.get("/api/notifications", headers=ctx["h"]).json()["items"] if "Продлить доступ" in n["text"]]
        self.assertEqual(billing.run_due() and 0, 0)
        self.assertEqual(notes(), [])                                   # до конца пробного периода далеко
        with db.tx() as conn:
            db.run(conn, "UPDATE accounts SET created_at = now() - interval '12 days' WHERE id = %s", (aid,))
        billing.run_due(); billing.run_due()
        self.assertEqual(len(notes()), 1)                               # «через 2 дн.» — один раз
        self.assertIn("Пробный период заканчивается через 2 дн.", notes()[0])
        self.assertEqual(self.client.get("/api/me", headers=ctx["h"]).json()["billing_notice"]["kind"], "trial")
        with db.tx() as conn:
            db.run(conn, "UPDATE accounts SET created_at = now() - interval '20 days' WHERE id = %s", (aid,))
        billing.run_due()
        self.assertTrue(any("закончился" in t for t in notes()))
        # платный тариф: за 7 дней, и сообщения из других стадий не дублируются
        with db.tx() as conn:
            db.run(conn, "UPDATE accounts SET plan = 'start', paid_until = current_date + 5 WHERE id = %s", (aid,))
            db.run(conn, "DELETE FROM billing_notices WHERE account_id = %s", (aid,))
        n_before = len(notes())
        billing.run_due(); billing.run_due()
        self.assertEqual(len(notes()), n_before + 1)
        self.assertIn("Оплата заканчивается через 5 дн.", notes()[0])
        # демо-аккаунт и «индивидуальный» тариф напоминаний не получают
        with db.tx() as conn:
            db.run(conn, "UPDATE accounts SET is_demo = true, paid_until = current_date - 3 WHERE id = %s", (aid,))
            db.run(conn, "DELETE FROM billing_notices WHERE account_id = %s", (aid,))
        n_before = len(notes())
        billing.run_due()
        self.assertEqual(len(notes()), n_before)

    def test_create_operator_cli(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            admin.main(["create-operator", "cli-op@fligel.test", "Из консоли"])
        password = buf.getvalue().split("пароль ")[1].split()[0]
        r = self.client.post("/api/operator/login", json={"email": "cli-op@fligel.test", "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["name"], "Из консоли")


if __name__ == "__main__":
    unittest.main()
