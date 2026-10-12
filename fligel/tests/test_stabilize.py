"""Раунд стабилизации: очереди без транзакции на время HTTP, письмо о сбросе пароля, одинаковое время ответа, секрет вебхука."""
import time
import re
import unittest

from test_app import Base, d  # noqa: F401

from app import config, db, mail, outbox, telegram


class OutboxTests(Base):
    def setUp(self):
        self.ctx = self.register(f"ob{id(self)}@example.ru")
        self._token, self._send = config.TELEGRAM_BOT_TOKEN, telegram.send_message
        config.TELEGRAM_BOT_TOKEN = "test-token"
        self.account_id = self.ctx["prop"]["account_id"]
        self.chat = id(self) % 900000000 + 100000000

    def tearDown(self):
        config.TELEGRAM_BOT_TOKEN, telegram.send_message = self._token, self._send

    def enqueue(self, text="тест"):
        with db.tx() as conn:
            telegram.enqueue(conn, self.account_id, self.chat, text)
            return db.one(conn, "SELECT id FROM telegram_outbox WHERE chat_id = %s AND text = %s ORDER BY created_at DESC LIMIT 1", (self.chat, text))["id"]

    def status(self, row_id):
        with db.tx() as conn:
            return db.one(conn, "SELECT status, attempts, last_error FROM telegram_outbox WHERE id = %s", (row_id,))

    def test_no_row_lock_and_status_sending_during_http(self):
        row_id = self.enqueue("во время отправки")
        seen = {}

        def send(chat_id, text):
            seen["status"] = self.status(row_id)["status"]
            # если бы транзакция держала блокировку строки, NOWAIT из другого соединения упал бы
            with db.tx() as conn:
                db.one(conn, "SELECT 1 FROM telegram_outbox WHERE id = %s FOR UPDATE NOWAIT", (row_id,))
                seen["free"] = True
        telegram.send_message = send
        telegram.process_outbox()
        self.assertEqual(seen["status"], "sending")
        self.assertTrue(seen["free"])
        self.assertEqual(self.status(row_id)["status"], "sent")

    def test_failure_goes_back_to_pending_with_pause(self):
        row_id = self.enqueue("сбой")

        def boom(chat_id, text):
            raise RuntimeError("Telegram недоступен")
        telegram.send_message = boom
        telegram.process_outbox()
        st = self.status(row_id)
        self.assertEqual((st["status"], st["attempts"]), ("pending", 1))
        self.assertIn("недоступен", st["last_error"])

    def test_crash_during_send_is_not_resent(self):
        row_id = self.enqueue("процесс упал")
        sent = []
        telegram.send_message = lambda c, t: sent.append(t)
        # имитируем падение: запись захвачена (sending), срок «аренды» истёк, отметки результата нет
        with db.tx() as conn:
            db.run(conn, "UPDATE telegram_outbox SET status = 'sending', next_attempt_at = now() - interval '1 minute' WHERE id = %s", (row_id,))
        telegram.process_outbox()
        self.assertEqual(sent, [])   # повторно не отправлено
        st = self.status(row_id)
        self.assertEqual(st["status"], "failed")
        self.assertIn("повторно не отправляем", st["last_error"])

    def test_claimed_rows_are_not_taken_twice(self):
        row_id = self.enqueue("один раз")
        first = outbox.claim("telegram_outbox", "SELECT id, chat_id, text, attempts FROM telegram_outbox WHERE id = %s AND status = 'pending'"
                                                " AND next_attempt_at <= now() FOR UPDATE SKIP LOCKED", (row_id,))
        second = outbox.claim("telegram_outbox", "SELECT id, chat_id, text, attempts FROM telegram_outbox WHERE id = %s AND status = 'pending'"
                                                 " AND next_attempt_at <= now() FOR UPDATE SKIP LOCKED", (row_id,))
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])


class ForgotPasswordTests(Base):
    def setUp(self):
        self.email = f"fp{id(self)}@example.ru"
        self.register(self.email)
        self._send, self._host = mail.send, config.SMTP_HOST
        config.SMTP_HOST = "smtp.test.local"
        self.seen = []
        mail.send = self._fake_send

    def tearDown(self):
        mail.flush()
        mail.send, config.SMTP_HOST = self._send, self._host

    def _fake_send(self, to, subject, body):
        # в момент отправки токен уже должен лежать в закоммиченной БД (письмо — после коммита)
        token = re.search(r"token=([\w\-]+)", body).group(1)
        with db.tx() as conn:
            self.seen.append(db.one(conn, "SELECT 1 AS x FROM password_resets WHERE token = %s", (token,)) is not None)
        time.sleep(0.4)   # «медленный SMTP»

    def timed(self, email):
        t = time.monotonic()
        r = self.client.post("/api/auth/forgot-password", json={"email": email})
        self.assertEqual(r.status_code, 200, r.text)
        return time.monotonic() - t

    def test_letter_is_sent_after_commit_and_does_not_slow_the_response(self):
        known = self.timed(self.email)
        unknown = self.timed("nobody-here@example.ru")
        mail.flush()
        self.assertEqual(self.seen, [True])
        # медленный SMTP (0,4 с) не виден в ответе, а времена для известного и неизвестного адреса почти равны
        self.assertLess(known, 0.6)
        self.assertLess(abs(known - unknown), 0.15)
        self.assertGreaterEqual(unknown, 0.3)

    def test_mail_failure_does_not_break_reset(self):
        def broken(*a):
            raise RuntimeError("SMTP недоступен")
        mail.send = broken
        with self.assertLogs("fligel.mail", level="ERROR"):
            self.assertLess(self.timed(self.email), 0.8)
            mail.flush()


class ConfigWarningsTests(Base):
    def setUp(self):
        self._saved = (config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_WEBHOOK_SECRET, config.MAX_BOT_TOKEN, config.MAX_WEBHOOK_SECRET)

    def tearDown(self):
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_WEBHOOK_SECRET, config.MAX_BOT_TOKEN, config.MAX_WEBHOOK_SECRET = self._saved

    def test_health_and_operator_warn_about_missing_webhook_secret(self):
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_WEBHOOK_SECRET = "tok", ""
        r = self.client.get("/health")
        self.assertTrue(any("TELEGRAM_WEBHOOK_SECRET" in w for w in r.json()["warnings"]))
        self.assertEqual(r.status_code, 200)   # предупреждение не роняет мониторинг
        config.TELEGRAM_WEBHOOK_SECRET = "secret"
        self.assertFalse(any("TELEGRAM" in w for w in self.client.get("/health").json()["warnings"]))
        config.TELEGRAM_BOT_TOKEN = ""
        config.MAX_BOT_TOKEN, config.MAX_WEBHOOK_SECRET = "tok", ""
        self.assertTrue(any("MAX_WEBHOOK_SECRET" in w for w in self.client.get("/health").json()["warnings"]))

    def test_operator_panel_gets_warnings(self):
        with db.tx() as conn:
            from app.auth import hash_password
            db.run(conn, "INSERT INTO operators (email, name, password_hash) VALUES ('w@fligel.test', 'W', %s) ON CONFLICT DO NOTHING", (hash_password("operator-pass-1"),))
        tok = self.client.post("/api/operator/login", json={"email": "w@fligel.test", "password": "operator-pass-1"}).json()["token"]
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_WEBHOOK_SECRET = "tok", ""
        data = self.client.get("/api/operator/accounts", headers={"Authorization": f"Bearer {tok}"}).json()
        self.assertTrue(any("TELEGRAM_WEBHOOK_SECRET" in w for w in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
