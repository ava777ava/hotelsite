"""Раунд 5, этап 4: публичный API (ключи, права, лимит), вебхуки (триггер БД, подпись, повторы, защита адреса)."""
import hmac
import hashlib
import json
import unittest

from test_app import Base, d  # noqa: F401

from app import config, db, ratelimit, webhooks
from app.errors import ApiError


class V1Base(Base):
    def setUp(self):
        ratelimit.reset()
        self._resolve, self._send, self._rpm = webhooks.resolve_host, webhooks.send, config.API_REQUESTS_PER_MINUTE
        webhooks.resolve_host = lambda host: ["93.184.216.34"]
        self.sent = []
        webhooks.send = lambda url, body, headers: self.sent.append((url, body, headers))

    def tearDown(self):
        webhooks.resolve_host, webhooks.send, config.API_REQUESTS_PER_MINUTE = self._resolve, self._send, self._rpm

    def key(self, ctx, scope="read", name="Сайт"):
        r = self.client.post("/api/keys", headers=ctx["h"], json={"name": name, "scope": scope})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["key"].startswith("flg_"))
        return r.json()

    @staticmethod
    def kh(key):
        return {"Authorization": f"Bearer {key['key']}"}


class ApiKeyTests(V1Base):
    def test_key_lifecycle_scopes_and_isolation(self):
        ctx = self.register("v1a@example.ru")
        other = self.register("v1b@example.ru")
        rk, wk = self.key(ctx), self.key(ctx, "write", "Бот")
        listing = self.client.get("/api/integrations", headers=ctx["h"]).json()["keys"]
        self.assertEqual({k["name"] for k in listing}, {"Сайт", "Бот"})
        self.assertNotIn("key", listing[0])                                   # полный ключ повторно не показывается
        self.assertEqual(listing[0]["prefix"][:4], "flg_")
        with db.tx() as conn:                                                   # в базе — только хэш
            self.assertEqual(db.one(conn, "SELECT count(*) AS n FROM api_keys WHERE key_hash = %s", (rk["key"],))["n"], 0)
        self.assertEqual(self.client.get("/api/v1/properties", headers=self.kh(rk)).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/properties").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/properties", headers={"Authorization": "Bearer flg_wrong"}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/properties", headers=ctx["h"]).status_code, 401)             # токен сотрудника — не ключ
        self.assertEqual(self.client.get("/api/me", headers=self.kh(rk)).status_code, 401)                     # ключ — не токен сотрудника
        room = ctx["rooms"][0]
        body = {"room_id": room["id"], "check_in": d(5), "check_out": d(7), "guest_name": "Через API"}
        self.assertEqual(self.client.post("/api/v1/bookings", headers=self.kh(rk), json=body).status_code, 403)   # read не пишет
        self.assertEqual(self.client.post("/api/v1/bookings", headers=self.kh(wk), json=body).status_code, 200)
        # чужой аккаунт не видит данные и не может занять чужой номер
        self.assertEqual(self.client.get("/api/v1/properties", headers=self.kh(self.key(other))).json()["items"][0]["id"], other["prop"]["id"])
        self.assertEqual(self.client.post("/api/v1/bookings", headers=self.kh(self.key(other, "write")), json=body).status_code, 404)
        # отзыв ключа действует сразу; только владелец управляет ключами
        self.assertEqual(self.client.delete(f"/api/keys/{listing[0]['id']}", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/keys/{listing[0]['id']}", headers=ctx["h"]).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/properties", headers=self.kh(rk if listing[0]["name"] == "Сайт" else wk)).status_code, 401)
        self.assertEqual(self.client.post("/api/keys", headers=ctx["h"], json={"name": "x", "scope": "admin"}).status_code, 422)
        self.assertEqual(self.client.post("/api/keys", headers=ctx["h"], json={"name": "", "scope": "read"}).status_code, 422)

    def test_rate_limit_per_key(self):
        ctx = self.register("v1c@example.ru")
        k = self.key(ctx)
        config.API_REQUESTS_PER_MINUTE = 3
        codes = [self.client.get("/api/v1/properties", headers=self.kh(k)).status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        self.assertIn("в минуту", self.client.get("/api/v1/properties", headers=self.kh(k)).json()["error"])

    def test_bookings_rooms_prices_endpoints(self):
        ctx = self.register("v1d@example.ru", rooms=(("Стандарт", 3, 3000),))
        wk = self.key(ctx, "write")
        h = self.kh(wk)
        rooms = self.client.get(f"/api/v1/rooms?property_id={ctx['prop']['id']}", headers=h).json()["items"]
        self.assertEqual([r["name"] for r in rooms], ["101", "102", "103"])
        self.assertEqual(len(self.client.get("/api/v1/room-types", headers=h).json()["items"]), 1)
        r = self.client.post("/api/v1/bookings", headers=h, json={"room_id": rooms[0]["id"], "check_in": d(3), "check_out": d(5), "guest_name": "Анна",
                                                                  "guest_email": "a@b.ru", "source": "avito", "id": "hack", "account_id": "x"})
        self.assertEqual(r.status_code, 200, r.text)
        b = r.json()
        self.assertEqual((float(b["total_price"]), b["source"], b["status"]), (6000.0, "other", "confirmed"))   # цена посчитана, лишние поля игнорируются
        self.assertEqual(self.client.post("/api/v1/bookings", headers=h, json={"room_id": rooms[0]["id"], "check_in": d(4), "check_out": d(6)}).status_code, 409)
        self.assertEqual(self.client.post("/api/v1/bookings", headers=h, json={"room_id": rooms[1]["id"], "check_in": d(4), "check_out": d(6), "status": "blocked"}).status_code, 422)
        self.assertEqual(self.client.get(f"/api/v1/bookings/{b['id']}", headers=h).json()["guest_name"], "Анна")
        lst = self.client.get(f"/api/v1/bookings?from={d(0)}&to={d(10)}", headers=h).json()["items"]
        self.assertEqual([x["id"] for x in lst], [b["id"]])
        self.assertEqual(self.client.get("/api/v1/bookings", headers=h).status_code, 422)
        self.assertEqual(self.client.get(f"/api/v1/bookings?from={d(0)}&to={d(900)}", headers=h).status_code, 422)
        self.assertEqual(self.client.get(f"/api/v1/bookings?from={d(0)}&to={d(10)}&status=bad", headers=h).status_code, 422)
        u = self.client.patch(f"/api/v1/bookings/{b['id']}", headers=h, json={"guest_name": "Анна П.", "status": "cancelled", "total_price": 1})
        self.assertEqual((u.status_code, u.json()["status"], u.json()["guest_name"]), (200, "cancelled", "Анна П."))
        self.assertEqual(self.client.patch(f"/api/v1/bookings/{b['id']}", headers=h, json={"id": "x"}).status_code, 422)
        self.assertEqual(self.client.get(f"/api/v1/bookings/{b['id']}", headers=self.kh(self.key(self.register('v1d2@example.ru')))).status_code, 404)
        tid = rooms[0]["room_type_id"]
        self.assertEqual(self.client.put("/api/v1/prices", headers=h, json={"room_type_id": tid, "date_from": d(10), "date_to": d(11), "price": 4500}).status_code, 200)
        pr = self.client.get(f"/api/v1/prices?room_type_id={tid}&from={d(9)}&to={d(12)}", headers=h).json()["items"]
        self.assertEqual([float(x["price"]) for x in pr], [3000.0, 4500.0, 4500.0])
        self.assertEqual(self.client.get(f"/api/v1/prices?room_type_id={tid}&from={d(9)}&to={d(9)}", headers=h).status_code, 422)
        self.assertEqual(self.client.put("/api/v1/prices", headers=self.kh(self.key(ctx)), json={"room_type_id": tid, "date_from": d(1), "date_to": d(1), "price": 1}).status_code, 403)


class WebhookTests(V1Base):
    def hook(self, ctx, url="https://hooks.example.com/fligel", **kw):
        r = self.client.post("/api/webhooks", headers=ctx["h"], json={"url": url, **kw})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_url_validation_ssrf_protection(self):
        ctx = self.register("wh1@example.ru")
        for url in ("http://hooks.example.com/x", "ftp://x.ru", "https://", "https://user:pw@hooks.example.com/x", "https://" + "a" * 600 + ".ru"):
            self.assertEqual(self.client.post("/api/webhooks", headers=ctx["h"], json={"url": url}).status_code, 422, url)
        for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "::1"):
            webhooks.resolve_host = lambda host, ip=ip: [ip]
            r = self.client.post("/api/webhooks", headers=ctx["h"], json={"url": "https://evil.example.com/x"})
            self.assertEqual(r.status_code, 422, ip)
            self.assertIn("внутренн", r.json()["error"])
        webhooks.resolve_host = lambda host: []
        self.assertEqual(self.client.post("/api/webhooks", headers=ctx["h"], json={"url": "https://nonexistent.example.com/x"}).status_code, 422)
        self.assertEqual(self.client.post("/api/webhooks", headers=ctx["h"], json={"url": "https://ok.example.com", "events": ["booking.exploded"]}).status_code, 422)

    def test_booking_events_signed_delivery_and_filters(self):
        ctx = self.register("wh2@example.ru")
        other = self.register("wh2b@example.ru")
        h_all = self.hook(ctx)
        h_cancel = self.hook(ctx, "https://cancel.example.com/h", events=["booking.cancelled"])
        self.hook(other, "https://other.example.com/h")
        room = ctx["rooms"][0]
        b = self.book(ctx, room, d(3), d(5), guest="Анна Петрова", guest_phone="+79001112233").json()
        self.book(ctx, ctx["rooms"][1], d(3), d(4), status="blocked")                      # закрытие дат — не событие
        self.book(other, other["rooms"][0], d(3), d(5))                                     # чужой аккаунт — чужой вебхук
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"guest_name": "Анна П.", "notes": "ждёт"})
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"status": "cancelled"})
        res = webhooks.process_outbox(50)
        self.assertEqual(res["failed"], 0)
        mine = [(u, json.loads(body), hd) for u, body, hd in self.sent if "other.example.com" not in u]
        events = [(u.split("//")[1].split("/")[0], p["event"]) for u, p, _ in mine]
        self.assertEqual(sorted(events), sorted([("hooks.example.com", "booking.created"), ("hooks.example.com", "booking.updated"),
                                                 ("hooks.example.com", "booking.cancelled"), ("cancel.example.com", "booking.cancelled")]))
        created = next(p for u, p, _ in mine if p["event"] == "booking.created")
        self.assertEqual((created["data"]["id"], created["data"]["guest_name"], created["data"]["check_in"], created["data"]["status"]), (b["id"], "Анна Петрова", d(3), "confirmed"))
        self.assertNotIn("account_id", created["data"])
        # подпись проверяется секретом вебхука; заголовки с типом события и номером доставки
        for u, body, hd in self.sent:
            secret = h_all["secret"] if "hooks.example.com" in u else (h_cancel["secret"] if "cancel.example.com" in u else None)
            if secret:
                self.assertEqual(hd["X-Fligel-Signature"], "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest())
                self.assertEqual(hd["X-Fligel-Event"], json.loads(body)["event"])
                self.assertEqual(hd["X-Fligel-Delivery"], json.loads(body)["id"])
        # повторный проход ничего не шлёт заново
        n = len(self.sent)
        webhooks.process_outbox(50)
        self.assertEqual(len(self.sent), n)
        listing = self.client.get("/api/integrations", headers=ctx["h"]).json()["webhooks"]
        self.assertTrue(all(w["last_status"] == "ok" for w in listing))

    def test_retries_backoff_failure_disable_and_test_event(self):
        ctx = self.register("wh3@example.ru")
        hk = self.hook(ctx)
        def boom(url, body, headers):
            raise RuntimeError("Сервер ответил кодом 500")
        webhooks.send = boom
        self.book(ctx, ctx["rooms"][0], d(3), d(5))
        r = webhooks.process_outbox()
        self.assertEqual((r["sent"], r["failed"]), (0, 0))                                  # ошибка — повтор позже, а не потеря
        with db.tx() as conn:
            row = db.one(conn, "SELECT attempts, status, next_attempt_at > now() AS later, last_error FROM webhook_deliveries WHERE webhook_id = %s", (hk["id"],))
            self.assertEqual((row["attempts"], row["status"], row["later"]), (1, "pending", True))
            self.assertIn("500", row["last_error"])
            db.run(conn, "UPDATE webhook_deliveries SET attempts = %s, next_attempt_at = now() WHERE webhook_id = %s", (webhooks.MAX_ATTEMPTS - 1, hk["id"]))
        r = webhooks.process_outbox()
        self.assertEqual(r["failed"], 1)                                                    # после последней попытки — окончательно «не доставлено»
        self.assertIn("ошибка", self.client.get("/api/integrations", headers=ctx["h"]).json()["webhooks"][0]["last_status"])
        # тестовое событие
        webhooks.send = lambda url, body, headers: self.sent.append((url, body, headers))
        self.assertEqual(self.client.post(f"/api/webhooks/{hk['id']}/test", headers=ctx["h"], json={}).status_code, 200)
        webhooks.process_outbox()
        self.assertEqual(json.loads(self.sent[-1][1])["event"], "booking.test")
        dl = self.client.get(f"/api/webhooks/{hk['id']}/deliveries", headers=ctx["h"]).json()["items"]
        self.assertEqual({x["status"] for x in dl}, {"sent", "failed"})
        # выключенный вебхук новых событий не получает
        self.client.patch(f"/api/webhooks/{hk['id']}", headers=ctx["h"], json={"enabled": False})
        n = len(self.sent)
        self.book(ctx, ctx["rooms"][1], d(8), d(9))
        webhooks.process_outbox()
        self.assertEqual(len(self.sent), n)

    def test_address_rechecked_on_delivery_and_permissions(self):
        ctx = self.register("wh4@example.ru")
        other = self.register("wh4b@example.ru")
        hk = self.hook(ctx)
        self.book(ctx, ctx["rooms"][0], d(3), d(5))
        webhooks.resolve_host = lambda host: ["10.1.2.3"]               # после регистрации адрес стал указывать внутрь сети
        webhooks.process_outbox()
        self.assertEqual(self.sent, [])
        with db.tx() as conn:
            self.assertIn("внутренн", db.one(conn, "SELECT last_error FROM webhook_deliveries WHERE webhook_id = %s", (hk["id"],))["last_error"])
        # чужой аккаунт не управляет вебхуком
        for call in (self.client.patch(f"/api/webhooks/{hk['id']}", headers=other["h"], json={"enabled": False}),
                     self.client.delete(f"/api/webhooks/{hk['id']}", headers=other["h"]),
                     self.client.post(f"/api/webhooks/{hk['id']}/test", headers=other["h"], json={}),
                     self.client.get(f"/api/webhooks/{hk['id']}/deliveries", headers=other["h"])):
            self.assertEqual(call.status_code, 404)
        self.assertEqual(self.client.delete(f"/api/webhooks/{hk['id']}", headers=ctx["h"]).status_code, 200)
        self.assertTrue(ApiError)


if __name__ == "__main__":
    unittest.main()
