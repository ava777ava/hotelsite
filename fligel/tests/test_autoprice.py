"""Раунд 5, этап 2: автоцены — правила, режимы (предлагать / применять), журнал, границы цен, ручные цены."""
import unittest
from datetime import date, timedelta
from decimal import Decimal

from test_app import Base, d  # noqa: F401

from app import autoprice, db, sync


class AutoPriceTests(Base):
    def setUpRegister(self, email, rooms=(("Стандарт", 10, 3000),)):
        ctx = self.register(email, rooms=rooms)
        ctx["type"] = ctx["prop"]["room_types"][0]
        return ctx

    def rule(self, ctx, **kw):
        body = {"kind": "weekend", "percent": 20, **kw}
        r = self.client.post("/api/autoprice/rules", headers=ctx["h"], json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def mode(self, ctx, mode, **kw):
        r = self.client.put("/api/autoprice/settings", headers=ctx["h"], json={"mode": mode, "horizon_days": 30, **kw})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def overview(self, ctx):
        return self.client.get("/api/autoprice", headers=ctx["h"]).json()

    def set_rate(self, ctx, day, **kw):
        r = self.client.put("/api/rates", headers=ctx["h"], json={"room_type_ids": [ctx["type"]["id"]], "date_from": str(day), "date_to": str(day), **kw})
        self.assertEqual(r.status_code, 200, r.text)

    def rate_price(self, ctx, day):
        with db.tx() as conn:
            r = db.one(conn, "SELECT price FROM rates WHERE room_type_id = %s AND date = %s", (ctx["type"]["id"], day))
        return float(r["price"]) if r and r["price"] is not None else None

    def test_suggest_mode_proposes_weekend_prices_and_apply_writes_calendar_and_journal(self):
        ctx = self.setUpRegister("ap1@example.ru")
        self.rule(ctx, kind="weekend", percent=20)
        res = self.mode(ctx, "suggest")
        self.assertEqual(res["applied"], 0)
        sug = self.overview(ctx)["suggestions"]
        self.assertTrue(sug)
        for s in sug:
            wd = date.fromisoformat(s["date"]).weekday()
            self.assertIn(wd, (4, 5))                     # пятница и суббота
            self.assertEqual(float(s["suggested_price"]), 3600.0)
            self.assertIn("выходной", s["reasons"])
        self.assertIsNone(self.rate_price(ctx, sug[0]["date"]))   # в режиме «предлагать» календарь не тронут
        r = self.client.post("/api/autoprice/apply", headers=ctx["h"], json={"ids": [sug[0]["id"]]})
        self.assertEqual(r.json(), {"count": 1})
        self.assertEqual(self.rate_price(ctx, sug[0]["date"]), 3600.0)
        ov = self.overview(ctx)
        self.assertEqual(len(ov["suggestions"]), len(sug) - 1)
        self.assertEqual((ov["changes"][0]["source"], float(ov["changes"][0]["new_price"]), ov["changes"][0]["user_name"]), ("suggestion", 3600.0, "Иван"))
        # «применить все» и «отклонить» работают
        self.assertEqual(self.client.post("/api/autoprice/apply", headers=ctx["h"], json={"ids": "all"}).json()["count"], len(sug) - 1)
        self.assertEqual(self.overview(ctx)["suggestions"], [])
        # цены попадают в расчёт стоимости брони
        sat = next(date.fromisoformat(s["date"]) for s in sug)
        q = self.client.get(f"/api/bookings/quote?room_id={ctx['rooms'][0]['id']}&check_in={sat}&check_out={sat + timedelta(days=1)}", headers=ctx["h"]).json()
        self.assertEqual(float(q["total"]), 3600.0)

    def test_dismiss_and_mode_off_clear_pending(self):
        ctx = self.setUpRegister("ap2@example.ru")
        self.rule(ctx, kind="weekend", percent=10)
        self.mode(ctx, "suggest")
        first = self.overview(ctx)["suggestions"][0]
        self.assertEqual(self.client.post("/api/autoprice/dismiss", headers=ctx["h"], json={"ids": [first["id"]]}).json(), {"count": 1})
        self.assertNotIn(first["id"], [s["id"] for s in self.overview(ctx)["suggestions"]])
        self.assertIsNone(self.rate_price(ctx, first["date"]))
        self.mode(ctx, "off")
        self.assertEqual(self.overview(ctx)["suggestions"], [])
        self.assertEqual(self.overview(ctx)["changes"], [])

    def test_auto_mode_low_occupancy_discount_is_idempotent_and_reverts(self):
        ctx = self.setUpRegister("ap3@example.ru", rooms=(("Стандарт", 4, 3000),))
        self.rule(ctx, kind="low_occupancy", percent=-10, days_ahead=7, threshold=50)
        res = self.mode(ctx, "auto")
        self.assertGreater(res["applied"], 0)
        # ближайшие 7 дней (включая сегодня) — скидка, дальше — нет
        for i in range(0, 8):
            self.assertEqual(self.rate_price(ctx, d(i)), 2700.0, i)
        self.assertIsNone(self.rate_price(ctx, d(8)))
        j = self.overview(ctx)["changes"]
        self.assertEqual({c["source"] for c in j}, {"auto"})
        self.assertIn("низкая загрузка", j[0]["reasons"])
        notes = self.client.get("/api/notifications", headers=ctx["h"]).json()["items"]
        self.assertTrue(any("Автоцены" in n["text"] for n in notes))
        # второй пересчёт ничего не меняет (цена не «съезжает» вниз каждый день)
        self.assertEqual(self.client.post("/api/autoprice/refresh", headers=ctx["h"], json={}).json()["applied"], 0)
        self.assertEqual(self.rate_price(ctx, d(3)), 2700.0)
        # загрузка выросла (3 из 4 номеров заняты на дату) — условие не выполняется, цена возвращается к базовой
        for room in ctx["rooms"][:3]:
            self.book(ctx, room, d(3), d(4))
        res = self.client.post("/api/autoprice/refresh", headers=ctx["h"], json={}).json()
        self.assertEqual(res["applied"], 1)
        self.assertEqual(self.rate_price(ctx, d(3)), 3000.0)
        self.assertEqual(self.rate_price(ctx, d(2)), 2700.0)

    def test_manual_price_is_respected_as_base_and_restored(self):
        ctx = self.setUpRegister("ap4@example.ru")
        sat = next(date.today() + timedelta(days=i) for i in range(1, 8) if (date.today() + timedelta(days=i)).weekday() == 5)
        self.set_rate(ctx, sat, price=5000)
        self.assertEqual(self.rate_price(ctx, sat), 5000.0)
        rule = self.rule(ctx, kind="weekend", percent=20)
        self.mode(ctx, "auto")
        self.assertEqual(self.rate_price(ctx, sat), 6000.0)           # 5000 (ручная) + 20 %, а не 3000 + 20 %
        self.client.post("/api/autoprice/refresh", headers=ctx["h"], json={})
        self.assertEqual(self.rate_price(ctx, sat), 6000.0)           # повторный пересчёт не копит проценты
        # правило выключили — цена возвращается к тому, что задал человек
        self.client.patch(f"/api/autoprice/rules/{rule['id']}", headers=ctx["h"], json={"enabled": False})
        self.client.post("/api/autoprice/refresh", headers=ctx["h"], json={})
        self.assertEqual(self.rate_price(ctx, sat), 5000.0)

    def test_min_max_price_limits_and_closed_dates(self):
        ctx = self.setUpRegister("ap5@example.ru")
        r = self.client.patch(f"/api/room-types/{ctx['type']['id']}", headers=ctx["h"], json={"min_price": 2900, "max_price": 3300})
        self.assertEqual((float(r.json()["min_price"]), float(r.json()["max_price"])), (2900.0, 3300.0))
        self.rule(ctx, kind="low_occupancy", percent=-30, days_ahead=5, threshold=60)
        self.rule(ctx, kind="weekend", percent=50)
        self.set_rate(ctx, d(1), closed=True)
        with db.tx() as conn:
            items = autoprice.compute(conn, db.one(conn, "SELECT account_id FROM room_types WHERE id = %s", (ctx["type"]["id"],))["account_id"], horizon=14)
        by = {x["date"]: x for x in items}
        self.assertNotIn(date.today() + timedelta(days=1), by)       # продажи закрыты — не трогаем
        for x in items:
            self.assertTrue(Decimal("2900") <= x["suggested_price"] <= Decimal("3300"), x)
        self.assertTrue(any("минимума" in x["reasons"] for x in items))
        self.assertTrue(any("максимума" in x["reasons"] for x in items))
        # перепутанные границы не ломают цены
        self.client.patch(f"/api/room-types/{ctx['type']['id']}", headers=ctx["h"], json={"min_price": 5000, "max_price": 1000})
        with db.tx() as conn:
            items = autoprice.compute(conn, db.one(conn, "SELECT account_id FROM room_types WHERE id = %s", (ctx["type"]["id"],))["account_id"], horizon=14)
        self.assertTrue(items)

    def test_last_free_room_and_holiday_rules(self):
        ctx = self.setUpRegister("ap6@example.ru", rooms=(("Стандарт", 3, 4000),))
        self.rule(ctx, kind="last_room", percent=15)
        for room in ctx["rooms"][:2]:
            self.book(ctx, room, d(4), d(5))
        self.mode(ctx, "auto")
        self.assertEqual(self.rate_price(ctx, d(4)), 4600.0)         # остался один номер из трёх
        self.assertIsNone(self.rate_price(ctx, d(5)))
        # праздники: 28 декабря + 60 дней — новогодние каникулы и 23 февраля
        acc = None
        with db.tx() as conn:
            acc = db.one(conn, "SELECT account_id FROM room_types WHERE id = %s", (ctx["type"]["id"],))["account_id"]
            db.run(conn, "DELETE FROM price_rules WHERE account_id = %s", (acc,))
            db.run(conn, "INSERT INTO price_rules (account_id, kind, percent) VALUES (%s, 'holiday', 25)", (acc,))
            items = autoprice.compute(conn, acc, today=date(2026, 12, 28), horizon=60)
        days = sorted(x["date"] for x in items)
        self.assertIn(date(2027, 1, 1), days)
        self.assertIn(date(2027, 1, 8), days)
        self.assertIn(date(2027, 2, 23), days)
        self.assertNotIn(date(2027, 1, 9), days)
        self.assertEqual(len(days), 9)
        self.assertTrue(all(float(x["suggested_price"]) == 5000.0 for x in items))
        self.assertIn("новогодние каникулы", [x for x in items if x["date"] == date(2027, 1, 3)][0]["reasons"])

    def test_scheduler_runs_once_a_day(self):
        ctx = self.setUpRegister("ap7@example.ru")
        self.rule(ctx, kind="weekend", percent=10)
        self.mode(ctx, "suggest")
        with db.tx() as conn:   # «вчера» — планировщик должен пересчитать
            db.run(conn, "UPDATE price_settings SET last_run_on = current_date - 1")
            db.run(conn, "DELETE FROM price_suggestions")
        self.assertGreaterEqual(autoprice.run_due(), 1)
        self.assertTrue(self.overview(ctx)["suggestions"])
        with db.tx() as conn:
            db.run(conn, "DELETE FROM price_suggestions")
        autoprice.run_due()                               # в тот же день повторно не считается
        self.assertEqual(self.overview(ctx)["suggestions"], [])
        self.assertIn("run_once", dir(sync))

    def test_validation_permissions_and_isolation(self):
        ctx = self.setUpRegister("ap8@example.ru")
        other = self.setUpRegister("ap8b@example.ru")
        r = self.client.post("/api/users", headers=ctx["h"], json={"name": "Админ", "email": "mgr-ap8@example.ru", "role": "manager", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "mgr-ap8@example.ru", "password": "password123"}).json()["token"]
        mh = {"Authorization": f"Bearer {tok}"}
        self.assertEqual(self.client.get("/api/autoprice", headers=mh).status_code, 200)                  # смотреть может администратор
        self.assertFalse(self.client.get("/api/autoprice", headers=mh).json()["can_edit"])
        self.assertEqual(self.client.post("/api/autoprice/rules", headers=mh, json={"kind": "weekend", "percent": 10}).status_code, 403)
        self.assertEqual(self.client.put("/api/autoprice/settings", headers=mh, json={"mode": "auto"}).status_code, 403)
        for bad in ({"kind": "magic", "percent": 10}, {"kind": "weekend", "percent": 0}, {"kind": "weekend", "percent": -5},
                    {"kind": "low_occupancy", "percent": 10}, {"kind": "weekend", "percent": 500}, {"kind": "weekend", "percent": "много"},
                    {"kind": "low_occupancy", "percent": -10, "threshold": 150}, {"kind": "weekend", "percent": 10, "room_type_id": other["type"]["id"]}):
            self.assertIn(self.client.post("/api/autoprice/rules", headers=ctx["h"], json=bad).status_code, (404, 422), bad)
        self.assertEqual(self.client.put("/api/autoprice/settings", headers=ctx["h"], json={"mode": "chaos"}).status_code, 422)
        rule = self.rule(other, kind="weekend", percent=10)
        self.assertEqual(self.client.patch(f"/api/autoprice/rules/{rule['id']}", headers=ctx["h"], json={"enabled": False}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/autoprice/rules/{rule['id']}", headers=ctx["h"]).status_code, 404)
        self.assertEqual(self.overview(ctx)["rules"], [])
        # чужие предложения применить нельзя
        self.mode(other, "suggest")
        theirs = self.overview(other)["suggestions"][0]
        self.assertEqual(self.client.post("/api/autoprice/apply", headers=ctx["h"], json={"ids": [theirs["id"]]}).json(), {"count": 0})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
