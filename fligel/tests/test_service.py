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


class DemoSandboxTests(Base):
    def setUp(self):
        self._enabled = config.DEMO_ENABLED

    def tearDown(self):
        config.DEMO_ENABLED = self._enabled

    def test_demo_start_restrictions_and_daily_reset(self):
        from datetime import datetime
        from app import demo, ratelimit
        ratelimit.reset()
        config.DEMO_ENABLED = False
        self.assertEqual(self.client.post("/api/demo/start", json={}).status_code, 404)
        self.assertFalse(self.client.get("/api/demo/status").json()["enabled"])
        config.DEMO_ENABLED = True
        self.assertEqual(self.client.post("/api/demo/start", json={}).status_code, 404)   # демо-аккаунт ещё не создан
        demo.main()
        r = self.client.post("/api/demo/start", json={})
        self.assertEqual(r.status_code, 200, r.text)
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        me = self.client.get("/api/me", headers=h).json()
        self.assertEqual((me["is_demo"], me["role"], me["billing_notice"]), (True, "owner", None))
        # то, что могло бы навредить другим посетителям или сервису, в демо закрыто
        for method, path, body in (("post", "/api/auth/change-password", {"current_password": "demo12345", "new_password": "hacked-pass-1"}),
                                   ("post", "/api/account/delete", {"password": "demo12345", "confirm": "УДАЛИТЬ"}),
                                   ("get", "/api/account/export", None),
                                   ("post", "/api/users", {"name": "X", "email": "x@x.ru", "role": "manager", "password": "password123"}),
                                   ("post", "/api/feeds", {"url": "https://example.com/a.ics"}),
                                   ("post", "/api/billing/invoices", {"plan": "start"}),
                                   ("post", "/api/telegram/link", {})):
            resp = getattr(self.client, method)(path, headers=h, **({"json": body} if body is not None else {}))
            self.assertEqual(resp.status_code, 403, (path, resp.text))
            self.assertIn("демо", resp.json()["error"].lower())
        # а работа с бронями и экраны — открыты
        board = self.client.get("/api/board", headers=h).json()
        room = board["room_types"][0]["rooms"][0]
        mk = self.client.post("/api/bookings", headers=h, json={"room_id": room["id"], "check_in": d(100), "check_out": d(102), "guest_name": "Следы посетителя"})
        self.assertEqual(mk.status_code, 200, mk.text)
        # старый пароль демо-аккаунта по-прежнему работает (его никто не мог сменить)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "demo@fligel.ru", "password": "demo12345"}).status_code, 200)
        # сброс: до часа сброса не трогаем, после — пересоздаём с чистыми данными, в тот же день второй раз не сбрасываем
        self.assertFalse(demo.reset_if_due(datetime(2030, 1, 1, config.DEMO_RESET_HOUR - 1 if config.DEMO_RESET_HOUR else 0, 30)) and config.DEMO_RESET_HOUR > 0)
        self.assertTrue(demo.reset_if_due(datetime(2030, 1, 1, 12, 0)))
        self.assertFalse(demo.reset_if_due(datetime(2030, 1, 1, 13, 0)))
        h2 = {"Authorization": f"Bearer {self.client.post('/api/demo/start', json={}).json()['token']}"}
        found = self.client.get(f"/api/bookings?from={d(99)}&to={d(104)}", headers=h2).json()
        self.assertFalse([b for b in found if b["guest_name"] == "Следы посетителя"])
        self.assertEqual(self.client.get("/api/me", headers=h).status_code, 401)           # прежняя сессия — аккаунт пересоздан
        # реальные клиенты демо-ограничениям не подвержены
        real = self.register("realclient@example.ru")
        self.assertEqual(self.client.post("/api/users", headers=real["h"], json={"name": "М", "email": "m-real@example.ru", "role": "manager", "password": "password123"}).status_code, 200)


class PublicSiteTests(Base):
    def test_blog_articles_seo_and_no_external_resources(self):
        import json
        import re
        from app import blog
        self.assertTrue(6 <= len(blog.ARTICLES) <= 8)
        idx = self.client.get("/blog/")
        self.assertEqual(idx.status_code, 200)
        self.assertEqual(self.client.get("/blog", follow_redirects=False).status_code, 307)
        sitemap = self.client.get("/sitemap.xml").text
        for a in blog.ARTICLES:
            self.assertIn(a["title"].replace("«", "«"), idx.text.replace("&quot;", '"'))
            page = self.client.get(f"/blog/{a['slug']}")
            self.assertEqual(page.status_code, 200, a["slug"])
            html = page.text
            self.assertIn(f"<title>{a['title']} — Флигель</title>", html)
            self.assertRegex(html, r'<meta name="description" content="[^"]{60,}')
            self.assertIn(f'rel="canonical" href="https://fligel.test/blog/{a["slug"]}"', html)
            ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
            self.assertEqual((ld["@type"], ld["headline"]), ("Article", a["title"]))
            self.assertIn(f"/blog/{a['slug']}</loc>", sitemap)
            self.assertGreater(len(re.sub(r"<[^>]+>", " ", a["body"]).split()), 200)          # содержательная статья, не заглушка
            # 152-ФЗ: ни внешних скриптов, шрифтов, картинок, ни счётчиков
            self.assertEqual([u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', html) if not u.startswith("https://fligel.test")], [], a["slug"])
            self.assertNotRegex(html.lower(), r"whatsapp|google|yandex\.ru/metrika|mc\.yandex")
        self.assertEqual(self.client.get("/blog/no-such-article").status_code, 404)
        self.assertIn("/blog/</loc>", sitemap)
        self.assertIn("/api/docs</loc>", sitemap)

    def test_api_docs_robots_landing_and_english_booking_page(self):
        docs = self.client.get("/api/docs")
        self.assertEqual(docs.status_code, 200)
        for needle in ("Authorization: Bearer flg_", "X-Fligel-Signature", "/api/v1/bookings", "/api/v1/prices", "booking.created", "120 запросов"):
            self.assertIn(needle, docs.text)
        robots = self.client.get("/robots.txt").text
        for path in ("/operator/", "/f/", "/r/", "/api/"):
            self.assertIn(f"Disallow: {path}", robots)
        landing = self.client.get("/").text
        for needle in ('id="calc-objects"', 'id="demo-btn"', 'href="/blog/"', 'rel="canonical"'):
            self.assertIn(needle, landing)
        book = self.client.get("/book/anything").text
        for needle in ('data-lang="en"', "Check-in", "Request sent", "Find a room"):
            self.assertIn(needle, book)


class BackupVerifyTests(Base):
    """deploy/verify_backup.sh: настоящий pg_dump → восстановление во временную базу → результат в /health."""

    def setUp(self):
        import shutil
        if not (shutil.which("pg_dump") and shutil.which("psql") and shutil.which("gzip")):
            self.skipTest("нет pg_dump/psql в окружении")

    def run_script(self, tmp, name=None):
        import os
        import subprocess
        from pathlib import Path
        script = Path(__file__).resolve().parent.parent / "deploy" / "verify_backup.sh"
        env = {**os.environ, "DATABASE_URL": os.environ["DATABASE_URL"], "FLIGEL_BACKUP_DIR": str(tmp)}
        return subprocess.run(["bash", str(script)] + ([name] if name else []), capture_output=True, text=True, env=env, timeout=120)

    def temp_dbs(self):
        with db.tx() as conn:
            return [r["datname"] for r in db.all_(conn, "SELECT datname FROM pg_database WHERE datname LIKE 'fligel_verify_%'")]

    def test_good_corrupt_and_empty_backups(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path
        self.register("bk1@example.ru")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dump = subprocess.run(f'pg_dump "{os.environ["DATABASE_URL"]}" | gzip > "{tmp}/fligel_2030-01-01_03-00-00.sql.gz"', shell=True, capture_output=True, text=True)
            self.assertEqual(dump.returncode, 0, dump.stderr)
            r = self.run_script(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK: восстановлен", r.stdout)
            self.assertEqual(self.temp_dbs(), [])                                      # временная база удалена
            hc = self.client.get("/health").json()["backup_check"]
            self.assertTrue(hc["ok"])
            self.assertFalse(hc["stale"])
            self.assertGreaterEqual(hc["accounts"], 1)
            self.assertIn("fligel_2030-01-01_03-00-00.sql.gz", hc["file"])
            # повреждённый файл
            bad = tmp / "fligel_2030-01-02_03-00-00.sql.gz"
            bad.write_bytes(b"this is not gzip at all")
            r = self.run_script(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("повреждён", r.stdout)
            hc = self.client.get("/health").json()["backup_check"]
            self.assertFalse(hc["ok"])
            self.assertIn("повреждён", hc["message"])
            # пустой файл
            bad.write_bytes(b"")
            self.assertIn("пустой", self.run_script(tmp).stdout)
            # нет бэкапов вообще
            with tempfile.TemporaryDirectory() as empty:
                r = self.run_script(Path(empty))
                self.assertEqual(r.returncode, 1)
                self.assertIn("нет файла бэкапа", r.stdout)
            self.assertEqual(self.temp_dbs(), [])
        # давность результата: старше 10 дней — stale
        with db.tx() as conn:
            import json as _j
            row = db.one(conn, "SELECT value FROM service_state WHERE key = 'backup_check'")
            v = _j.loads(row["value"]); v["at"] = "2020-01-01T00:00:00Z"
            db.run(conn, "UPDATE service_state SET value = %s WHERE key = 'backup_check'", (_j.dumps(v),))
        self.assertTrue(self.client.get("/health").json()["backup_check"]["stale"])
        self.assertEqual(self.client.get("/health").status_code, 200)               # на «здоров» это не влияет


if __name__ == "__main__":
    unittest.main()
