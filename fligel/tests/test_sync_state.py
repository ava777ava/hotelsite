"""Режим отладки и состояние синхронизации: сырые .ics, экран состояния, предупреждение «площадка не забирала наш календарь»."""
import unittest
from datetime import date

from test_app import Base, d  # noqa: F401
from test_sync_formats import cal, ev

from app import config, db, notify, sync, syncdebug, telegram


class SyncStateTests(Base):
    def setUp(self):
        self.ctx = self.register(f"sst{id(self)}@example.ru")
        self.room = self.ctx["rooms"][0]
        self.account = self.ctx["prop"]["account_id"]
        self._orig = sync.fetch
        self.body = cal(ev("UID:u1", f"DTSTART;VALUE=DATE:{d(5).replace('-', '')}", f"DTEND;VALUE=DATE:{d(7).replace('-', '')}", "SUMMARY:Занято"))
        sync.fetch = lambda url: self.body
        self.client.put("/api/sync/debug", headers=self.ctx["h"], json={"enabled": True})   # по умолчанию режим отладки выключен

    def tearDown(self):
        sync.fetch = self._orig

    def feed(self, channel="avito"):
        r = self.client.post("/api/feeds", headers=self.ctx["h"], json={"room_id": self.room["id"], "channel": channel, "url": "https://example.com/c.ics"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def received(self, feed_id):
        return self.client.get("/api/sync/snapshots", headers=self.ctx["h"], params={"kind": "received", "feed_id": feed_id}).json()["items"]

    def test_received_calendar_is_saved_deduplicated_and_limited_to_ten(self):
        fid = self.feed()
        items = self.received(fid)
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["events"], items[0]["status"]), (1, "ok"))
        self.client.post(f"/api/feeds/{fid}/sync", headers=self.ctx["h"])   # тот же календарь — копия не плодится
        items = self.received(fid)
        self.assertEqual((len(items), items[0]["seen_count"]), (1, 2))
        for i in range(12):                                                # разные календари — хранятся только 10 последних
            self.body = cal(ev(f"UID:v{i}", f"DTSTART;VALUE=DATE:{d(10 + i).replace('-', '')}", f"DTEND;VALUE=DATE:{d(11 + i).replace('-', '')}"))
            self.client.post(f"/api/feeds/{fid}/sync", headers=self.ctx["h"])
        items = self.received(fid)
        self.assertEqual(len(items), syncdebug.SNAPSHOTS_KEEP)
        raw = self.client.get(f"/api/sync/snapshots/{items[0]['id']}", headers=self.ctx["h"]).json()
        self.assertIn("BEGIN:VCALENDAR", raw["body"])
        self.assertIn("UID:v11", raw["body"])

    def test_unparsable_calendar_is_kept_with_error_note(self):
        self.body = "<html>Включите JavaScript</html>"
        fid = self.client.post("/api/feeds", headers=self.ctx["h"], json={"room_id": self.room["id"], "channel": "yandex", "url": "https://example.com/c.ics"}).json()["id"]
        items = self.received(fid)
        self.assertEqual((len(items), items[0]["status"]), (1, "error"))
        self.assertIn("нет BEGIN:VCALENDAR", items[0]["note"])

    def test_served_calendar_is_saved_with_user_agent_and_not_duplicated(self):
        with db.tx() as conn:
            token = db.one(conn, "SELECT ical_token FROM rooms WHERE id = %s", (self.room["id"],))["ical_token"]
        for _ in range(3):
            r = self.client.get(f"/ical/{token}/avito.ics", headers={"User-Agent": "AvitoCalendarBot/1.0"})
            self.assertEqual(r.status_code, 200)
        items = self.client.get("/api/sync/snapshots", headers=self.ctx["h"], params={"kind": "served", "target_id": self.room["id"], "channel": "avito"}).json()["items"]
        self.assertEqual(len(items), 1)                       # DTSTAMP меняется в каждом ответе, но это не «новый» календарь
        self.assertEqual((items[0]["seen_count"], items[0]["user_agent"]), (3, "AvitoCalendarBot/1.0"))
        # после новой брони отданный календарь другой — появляется вторая копия
        self.book(self.ctx, self.room, d(3), d(4))
        self.client.get(f"/ical/{token}/avito.ics")
        items = self.client.get("/api/sync/snapshots", headers=self.ctx["h"], params={"kind": "served", "target_id": self.room["id"], "channel": "avito"}).json()["items"]
        self.assertEqual(len(items), 2)
        self.assertIn("BEGIN:VEVENT", self.client.get(f"/api/sync/snapshots/{items[0]['id']}", headers=self.ctx["h"]).json()["body"])

    def test_debug_is_off_by_default(self):
        other = self.register(f"ssdef{id(self)}@example.ru")
        self.assertFalse(self.client.get("/api/sync/state", headers=other["h"]).json()["debug"])
        fid = self.client.post("/api/feeds", headers=other["h"], json={"room_id": other["rooms"][0]["id"], "channel": "avito", "url": "https://example.com/c.ics"}).json()["id"]
        self.assertEqual(self.client.get("/api/sync/snapshots", headers=other["h"], params={"kind": "received", "feed_id": fid}).json()["items"], [])

    def test_debug_off_stores_nothing_and_clears_saved(self):
        fid = self.feed()
        self.assertEqual(len(self.received(fid)), 1)
        r = self.client.put("/api/sync/debug", headers=self.ctx["h"], json={"enabled": False})
        self.assertFalse(r.json()["debug"])
        self.assertEqual(self.received(fid), [])
        self.client.post(f"/api/feeds/{fid}/sync", headers=self.ctx["h"])
        self.assertEqual(self.received(fid), [])
        self.assertFalse(self.client.get("/api/sync/state", headers=self.ctx["h"]).json()["debug"])

    def test_snapshots_are_owner_only_and_isolated_between_accounts(self):
        fid = self.feed()
        snap_id = self.received(fid)[0]["id"]
        email = f"sstm{id(self)}@example.ru"
        self.client.post("/api/users", headers=self.ctx["h"], json={"name": "Админ", "email": email, "password": "password123", "role": "manager"})
        tok = self.client.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]
        mgr = {"Authorization": f"Bearer {tok}"}
        self.assertEqual(self.client.get("/api/sync/snapshots", headers=mgr, params={"kind": "received", "feed_id": fid}).status_code, 403)
        self.assertEqual(self.client.get(f"/api/sync/snapshots/{snap_id}", headers=mgr).status_code, 403)
        self.assertEqual(self.client.get("/api/sync/state", headers=mgr).status_code, 200)   # состояние видит и администратор
        other = self.register(f"sstx{id(self)}@example.ru")
        self.assertEqual(self.client.get(f"/api/sync/snapshots/{snap_id}", headers=other["h"]).status_code, 404)

    def test_state_screen_data(self):
        fid = self.feed()
        with db.tx() as conn:
            token = db.one(conn, "SELECT ical_token FROM rooms WHERE id = %s", (self.room["id"],))["ical_token"]
        self.client.get(f"/ical/{token}/avito.ics", headers={"User-Agent": "Bot/2"})
        st = self.client.get("/api/sync/state", headers=self.ctx["h"]).json()
        row = next(x for x in st["items"] if x["feed_id"] == fid)
        self.assertEqual((row["channel_label"], row["last_status"], row["export_count"], row["last_user_agent"]), ("Авито", "ok", 1, "Bot/2"))
        self.assertEqual((row["last_run"]["events"], row["last_run"]["echoes"], row["errors_24h"]), (1, 0, 0))
        self.assertIsNotNone(row["exported_at"])
        self.assertEqual((st["stale_hours"], st["stale"]), (6, 0))

    def test_echo_count_and_errors_are_reported(self):
        # наш календарь «виден» площадке, потом она возвращает его как своё событие → эхо отбрасывается и считается
        with db.tx() as conn:
            token = db.one(conn, "SELECT ical_token FROM rooms WHERE id = %s", (self.room["id"],))["ical_token"]
        self.book(self.ctx, self.room, d(10), d(12), guest="Наш гость")
        self.client.get(f"/ical/{token}/avito.ics")
        self.body = cal(ev("UID:echo1", f"DTSTART;VALUE=DATE:{d(10).replace('-', '')}", f"DTEND;VALUE=DATE:{d(12).replace('-', '')}", "SUMMARY:Занято"))
        fid = self.feed()
        row = next(x for x in self.client.get("/api/sync/state", headers=self.ctx["h"]).json()["items"] if x["feed_id"] == fid)
        self.assertEqual((row["last_run"]["events"], row["last_run"]["echoes"], int(row["echoes_7d"])), (1, 1, 1))
        sync.fetch = lambda url: (_ for _ in ()).throw(RuntimeError("Площадка ответила кодом 503"))
        self.client.post(f"/api/feeds/{fid}/sync", headers=self.ctx["h"])
        row = next(x for x in self.client.get("/api/sync/state", headers=self.ctx["h"]).json()["items"] if x["feed_id"] == fid)
        self.assertEqual((row["last_status"], row["errors_24h"]), ("error", 1))
        self.assertIn("503", row["last_error"])


class FetchGuardTests(Base):
    """Календарь площадки забираем только с публичных адресов (SSRF): внутренняя сеть, метаданные облака, редиректы внутрь."""

    def setUp(self):
        self._base = config.PUBLIC_BASE_URL
        config.PUBLIC_BASE_URL = "https://fligel.example"      # боевой режим: проверка включена
        self._resolve = sync.webhooks.resolve_host

    def tearDown(self):
        config.PUBLIC_BASE_URL = self._base
        sync.webhooks.resolve_host = self._resolve

    def test_internal_addresses_are_refused(self):
        for url in ("http://127.0.0.1/x.ics", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/c.ics", "https://172.16.3.4/c.ics",
                    "http://192.168.1.1/c.ics", "http://[::1]/c.ics", "http://100.64.0.1/c.ics", "http://0.0.0.0/c.ics"):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                sync._guard(url)
        with self.assertRaises(RuntimeError):
            sync._guard("ftp://example.com/c.ics")

    def test_hostname_resolving_to_private_ip_is_refused(self):
        sync.webhooks.resolve_host = lambda host: ["10.1.2.3"]
        with self.assertRaises(RuntimeError):
            sync._guard("https://innocent.example.com/c.ics")
        sync.webhooks.resolve_host = lambda host: ["93.184.216.34", "10.1.2.3"]   # хоть один внутренний — отказ
        with self.assertRaises(RuntimeError):
            sync._guard("https://mixed.example.com/c.ics")
        sync.webhooks.resolve_host = lambda host: ["93.184.216.34"]
        sync._guard("https://public.example.com/c.ics")   # публичный — проходит
        sync.webhooks.resolve_host = lambda host: []
        with self.assertRaises(RuntimeError):
            sync._guard("https://nothing.example.com/c.ics")

    def test_redirect_into_internal_network_is_not_followed(self):
        import httpx
        sync.webhooks.resolve_host = lambda host: ["10.0.0.1"] if host == "internal.local" else ["93.184.216.34"]
        seen = []

        def handler(request):
            seen.append(str(request.url))
            if request.url.host == "calendar.example.com":
                return httpx.Response(302, headers={"location": "http://internal.local/secret"})
            return httpx.Response(200, text="SECRET")
        real = httpx.Client
        sync.httpx.Client = lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
        try:
            with self.assertRaisesRegex(RuntimeError, "внутреннюю сеть"):
                sync.fetch("https://calendar.example.com/c.ics")
        finally:
            sync.httpx.Client = real
        self.assertEqual(seen, ["https://calendar.example.com/c.ics"])   # до внутреннего адреса запрос не дошёл

    def test_normal_redirect_is_followed(self):
        import httpx
        sync.webhooks.resolve_host = lambda host: ["93.184.216.34"]

        def handler(request):
            if request.url.path == "/old.ics":
                return httpx.Response(301, headers={"location": "/new.ics"})
            return httpx.Response(200, text="BEGIN:VCALENDAR\nEND:VCALENDAR")
        real = httpx.Client
        sync.httpx.Client = lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
        try:
            self.assertIn("VCALENDAR", sync.fetch("https://calendar.example.com/old.ics"))
        finally:
            sync.httpx.Client = real

    def test_feed_form_rejects_numeric_internal_address(self):
        ctx = self.register(f"fg{id(self)}@example.ru")
        for url in ("http://172.16.0.9/c.ics", "http://169.254.169.254/x", "https://[::1]/c.ics"):
            r = self.client.post("/api/feeds", headers=ctx["h"], json={"room_id": ctx["rooms"][0]["id"], "channel": "avito", "url": url})
            self.assertEqual(r.status_code, 422, url)

    def test_error_snapshot_of_foreign_response_is_truncated(self):
        ctx = self.register(f"fgs{id(self)}@example.ru")
        self.client.put("/api/sync/debug", headers=ctx["h"], json={"enabled": True})
        orig = sync.fetch
        sync.fetch = lambda url: "<html>" + "x" * 100000
        try:
            fid = self.client.post("/api/feeds", headers=ctx["h"], json={"room_id": ctx["rooms"][0]["id"], "channel": "avito", "url": "https://example.com/c.ics"}).json()["id"]
        finally:
            sync.fetch = orig
        snap = self.client.get("/api/sync/snapshots", headers=ctx["h"], params={"kind": "received", "feed_id": fid}).json()["items"][0]
        self.assertLessEqual(snap["size"], 20000)


class StaleExportTests(Base):
    def setUp(self):
        self.ctx = self.register(f"stale{id(self)}@example.ru")
        self.room = self.ctx["rooms"][0]
        self.account = self.ctx["prop"]["account_id"]
        self._orig, self._token = sync.fetch, config.TELEGRAM_BOT_TOKEN
        sync.fetch = lambda url: cal()
        self.fid = self.client.post("/api/feeds", headers=self.ctx["h"], json={"room_id": self.room["id"], "channel": "avito", "url": "https://example.com/c.ics"}).json()["id"]

    def tearDown(self):
        sync.fetch, config.TELEGRAM_BOT_TOKEN = self._orig, self._token

    def alerts(self):
        with db.tx() as conn:
            return db.one(conn, "SELECT count(*) AS n FROM sync_alerts WHERE account_id = %s", (self.account,))["n"]

    def bell(self):
        return [n for n in self.client.get("/api/notifications", headers=self.ctx["h"]).json()["items"] if "не забирала наш календарь" in n["text"]]

    def age(self, hours, fetched=True):
        with db.tx() as conn:
            db.run(conn, "UPDATE ical_feeds SET created_at = now() - make_interval(hours => %s) WHERE id = %s", (hours, self.fid))
            db.run(conn, "DELETE FROM ical_exports WHERE target_id = %s", (self.room["id"],))
            if fetched:
                db.run(conn, "INSERT INTO ical_exports (target_id, channel, last_fetched_at) VALUES (%s, 'avito', now() - make_interval(hours => %s))", (self.room["id"], hours))

    def test_no_warning_before_threshold(self):
        self.age(5)
        syncdebug.check_stale()
        self.assertEqual(self.alerts(), 0)

    def test_warning_after_six_hours_once_and_cleared_after_fetch(self):
        self.age(7)
        syncdebug.check_stale()
        self.assertEqual(self.alerts(), 1)
        self.assertEqual(len(self.bell()), 1)
        syncdebug.check_stale()                      # повторный проход — то же предупреждение, второго уведомления нет
        self.assertEqual((self.alerts(), len(self.bell())), (1, 1))
        badges = self.client.get("/api/badges", headers=self.ctx["h"]).json()
        self.assertEqual((badges["conflicts"], badges["export_stale"]), (0, 1))   # не выдаём за двойную бронь
        st = self.client.get("/api/sync/state", headers=self.ctx["h"]).json()
        self.assertEqual(st["stale"], 1)
        with db.tx() as conn:
            token = db.one(conn, "SELECT ical_token FROM rooms WHERE id = %s", (self.room["id"],))["ical_token"]
        self.client.get(f"/ical/{token}/avito.ics")  # площадка забрала календарь
        syncdebug.check_stale()
        self.assertEqual(self.alerts(), 0)
        self.assertEqual(self.client.get("/api/badges", headers=self.ctx["h"]).json()["export_stale"], 0)

    def test_never_fetched_feed_warns_after_threshold_from_connection(self):
        self.age(7, fetched=False)
        syncdebug.check_stale()
        self.assertEqual(self.alerts(), 1)

    def test_disabled_feed_and_demo_are_not_warned(self):
        self.age(10)
        with db.tx() as conn:
            db.run(conn, "UPDATE ical_feeds SET enabled = false WHERE id = %s", (self.fid,))
        syncdebug.check_stale()
        self.assertEqual(self.alerts(), 0)

    def test_telegram_gets_the_warning(self):
        config.TELEGRAM_BOT_TOKEN = "t"
        sent = []
        orig = telegram.send_message
        telegram.send_message = lambda chat, text: sent.append(text)
        try:
            code = self.client.post("/api/telegram/link", headers=self.ctx["h"]).json()["pending_code"]
            self.client.post("/api/telegram/webhook", json={"message": {"text": f"/start {code}", "chat": {"id": id(self) % 900000000 + 100000000}}})
            telegram.process_outbox()
            sent.clear()
            self.age(8)
            syncdebug.check_stale()
            telegram.process_outbox()
        finally:
            telegram.send_message = orig
        self.assertTrue(any("не забирала наш календарь" in t for t in sent), sent)


if __name__ == "__main__":
    unittest.main()
