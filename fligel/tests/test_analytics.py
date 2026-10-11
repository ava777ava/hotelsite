"""Раунд 5, этап 2: прогноз вперёд, темп бронирований, окно бронирования, доходность каналов, сводка для бухгалтера."""
import unittest
from datetime import date, timedelta

from test_app import Base, d  # noqa: F401

from app import db
from app.api.reports import _shift_years


def set_created(booking_id, days_ago: int):
    with db.tx() as conn:
        db.run(conn, "UPDATE bookings SET created_at = now() - make_interval(days => %s) WHERE id = %s", (days_ago, booking_id))


class ForecastTests(Base):
    def test_forecast_horizons_and_year_ago_pace_vs_final(self):
        ctx = self.register("fc1@example.ru", rooms=(("Стандарт", 10, 3000),))
        self.book(ctx, ctx["rooms"][0], d(3), d(7))                         # 4 ночи × 3000 = 12 000, внутри 30 дней
        self.book(ctx, ctx["rooms"][1], d(40), d(42))                       # 2 ночи, только в горизонтах 60 и 90
        fc = self.client.get("/api/analytics/forecast", headers=ctx["h"]).json()
        self.assertEqual([h["days"] for h in fc["horizons"]], [30, 60, 90])
        h30, h60, h90 = fc["horizons"]
        self.assertEqual((h30["sold_nights"], h60["sold_nights"], h90["sold_nights"]), (4, 6, 6))
        self.assertAlmostEqual(h30["occupancy"], round(4 * 100 / (10 * 30), 1))
        self.assertEqual(float(h30["revenue"]), 12000.0)
        self.assertEqual(float(h60["revenue"]), 18000.0)
        # год назад в системе ничего не было: сравнивать не с чем, и это сказано явно
        self.assertFalse(fc["pace_available"])
        self.assertIsNone(h30["year_ago_pace"])
        self.assertIsNone(h30["year_ago_final"])
        # появились брони прошлого года: одна «видна» на ту же дату год назад (создана 400 дней назад), вторая создана позже
        ly_in = _shift_years(date.today(), -1) + timedelta(days=5)
        early = self.client.post("/api/bookings", headers=ctx["h"], json={"room_id": ctx["rooms"][2]["id"], "check_in": ly_in.isoformat(),
                                                                          "check_out": (ly_in + timedelta(days=3)).isoformat()}).json()
        late = self.client.post("/api/bookings", headers=ctx["h"], json={"room_id": ctx["rooms"][3]["id"], "check_in": ly_in.isoformat(),
                                                                         "check_out": (ly_in + timedelta(days=2)).isoformat()}).json()
        set_created(early["id"], 400)
        set_created(late["id"], 20)
        fc = self.client.get("/api/analytics/forecast", headers=ctx["h"]).json()
        h30 = fc["horizons"][0]
        self.assertTrue(fc["pace_available"])
        self.assertEqual(h30["year_ago_pace"]["sold_nights"], 3)    # только то, что уже было забронировано год назад
        self.assertEqual(h30["year_ago_final"]["sold_nights"], 5)   # итог того же периода: обе брони
        self.assertEqual(h30["revenue_vs_final"], round((12000 - 15000) * 100 / 15000, 1))
        self.assertEqual(h30["revenue_vs_pace"], round((12000 - 9000) * 100 / 9000, 1))

    def test_forecast_scopes_to_account_and_manager_only(self):
        ctx = self.register("fc2@example.ru")
        other = self.register("fc2b@example.ru")
        self.book(other, other["rooms"][0], d(3), d(6))
        self.assertEqual(self.client.get("/api/analytics/forecast", headers=ctx["h"]).json()["horizons"][0]["sold_nights"], 0)
        r = self.client.post("/api/users", headers=ctx["h"], json={"name": "М", "email": "maid-fc2@example.ru", "role": "housekeeper", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "maid-fc2@example.ru", "password": "password123"}).json()["token"]
        for path in ("forecast", "pace", "lead-time", "channels", "accountant", "accountant.csv"):
            self.assertEqual(self.client.get(f"/api/analytics/{path}", headers={"Authorization": f"Bearer {tok}"}).status_code, 403, path)
            self.assertEqual(self.client.get(f"/api/analytics/{path}").status_code, 401, path)
        self.assertEqual(r.status_code, 200)
        # чужой объект указать нельзя
        self.assertEqual(self.client.get(f"/api/analytics/forecast?property_id={other['prop']['id']}", headers=ctx["h"]).status_code, 404)


class PaceLeadChannelTests(Base):
    def test_booking_pace_by_source_week_over_week(self):
        ctx = self.register("pc1@example.ru")
        a = self.book(ctx, ctx["rooms"][0], d(10), d(12), source="avito").json()
        self.book(ctx, ctx["rooms"][1], d(10), d(13), source="direct")
        b = self.book(ctx, ctx["rooms"][2], d(10), d(11), source="avito").json()
        c_ = self.book(ctx, ctx["rooms"][3], d(10), d(11), source="avito").json()
        old = self.book(ctx, ctx["rooms"][4], d(10), d(11), source="avito").json()
        cancelled = self.book(ctx, ctx["rooms"][5], d(10), d(11), source="avito").json()
        self.client.patch(f"/api/bookings/{cancelled['id']}", headers=ctx["h"], json={"status": "cancelled"})
        set_created(b["id"], 9)      # прошлая неделя
        set_created(c_["id"], 12)    # прошлая неделя
        set_created(old["id"], 30)   # раньше — в темп не входит
        p = self.client.get("/api/analytics/pace", headers=ctx["h"]).json()
        self.assertEqual((p["total"]["bookings"], p["total"]["prev_bookings"]), (2, 2))
        src = {s["source"]: s for s in p["sources"]}
        self.assertEqual((src["avito"]["bookings"], src["avito"]["prev_bookings"]), (1, 2))
        self.assertEqual((src["direct"]["bookings"], src["direct"]["prev_bookings"]), (1, 0))
        self.assertEqual(src["avito"]["nights"], 2)
        self.assertEqual(len(p["daily"]), 14)
        self.assertEqual(sum(x["bookings"] for x in p["daily"]), 4)
        self.assertEqual(a["status"], "confirmed")

    def test_lead_time_and_average_stay_by_channel(self):
        ctx = self.register("pc2@example.ru")
        x = self.book(ctx, ctx["rooms"][0], d(30), d(33), source="direct").json()   # 3 ночи
        y = self.book(ctx, ctx["rooms"][1], d(30), d(35), source="direct").json()   # 5 ночей
        z = self.book(ctx, ctx["rooms"][2], d(5), d(6), source="avito").json()      # 1 ночь
        set_created(x["id"], 10)     # окно: 40 дней
        set_created(y["id"], 0)      # окно: 30 дней
        set_created(z["id"], 0)      # окно: 5 дней
        lt = self.client.get(f"/api/analytics/lead-time?from={d(0)}&to={d(60)}", headers=ctx["h"]).json()
        src = {s["source"]: s for s in lt["by_source"]}
        self.assertEqual((src["direct"]["bookings"], src["direct"]["lead"], src["direct"]["stay"]), (2, 35.0, 4.0))
        self.assertEqual((src["avito"]["lead"], src["avito"]["stay"]), (5.0, 1.0))
        self.assertEqual(lt["overall"]["bookings"], 3)
        self.assertEqual(lt["overall"]["lead"], round((40 + 30 + 5) / 3, 1))
        by = {b["label"]: b["bookings"] for b in lt["buckets"]}
        self.assertEqual((by["за 2–7 дней"], by["за 8–30 дней"], by["за 31–90 дней"]), (1, 1, 1))
        # слишком длинный или обратный период — понятная ошибка
        self.assertEqual(self.client.get(f"/api/analytics/lead-time?from={d(10)}&to={d(5)}", headers=ctx["h"]).status_code, 422)
        self.assertEqual(self.client.get(f"/api/analytics/lead-time?from={d(-500)}&to={d(0)}", headers=ctx["h"]).status_code, 422)

    def test_channel_profitability_with_commission_and_cancellations(self):
        ctx = self.register("pc3@example.ru")
        self.client.put("/api/channel-commissions", headers=ctx["h"], json={"items": [{"channel": "avito", "percent": 10}]})
        self.book(ctx, ctx["rooms"][0], d(2), d(4), source="avito", total_price=6000)    # 2 ночи
        gone = self.book(ctx, ctx["rooms"][1], d(2), d(3), source="avito", total_price=2000).json()
        self.client.patch(f"/api/bookings/{gone['id']}", headers=ctx["h"], json={"status": "cancelled"})
        self.book(ctx, ctx["rooms"][2], d(2), d(4), source="direct", total_price=8000)
        ch = self.client.get(f"/api/analytics/channels?from={d(0)}&to={d(30)}", headers=ctx["h"]).json()
        it = {x["source"]: x for x in ch["items"]}
        av = it["avito"]
        self.assertEqual((av["bookings"], av["cancelled"], av["cancel_share"]), (1, 1, 50.0))
        self.assertEqual((float(av["revenue"]), float(av["commission"]), float(av["net_revenue"])), (6000.0, 600.0, 5400.0))
        self.assertEqual((float(av["avg_price"]), float(av["net_avg_price"])), (3000.0, 2700.0))
        self.assertEqual(float(it["direct"]["net_revenue"]), 8000.0)
        self.assertEqual(ch["items"][0]["source"], "direct")  # по чистой выручке: сайт (8000) выше Авито (5400)
        self.assertEqual(float(ch["totals"]["net_revenue"]), 13400.0)


class HomeHintsTests(Base):
    def test_hints_low_occupancy_dates_and_one_night_gaps(self):
        ctx = self.register("hint1@example.ru", rooms=(("Стандарт", 2, 3000),))
        r1, r2 = ctx["rooms"]
        self.book(ctx, r1, d(2), d(4))
        self.book(ctx, r1, d(5), d(7))          # между ними свободна ровно одна ночь: с 4-го на 5-е
        self.book(ctx, r2, d(8), d(10))
        self.book(ctx, r2, d(10), d(12))        # встык — это не «окно»
        self.book(ctx, r2, d(13), d(15))
        self.client.post("/api/bookings", headers=ctx["h"], json={"room_id": r2["id"], "check_in": d(12), "check_out": d(13), "status": "blocked"})  # закрыто — тоже не «окно»
        hn = self.client.get("/api/today?summary=1", headers=ctx["h"]).json()["summary"]["hints"]
        self.assertEqual([(g["room_name"], g["date"]) for g in hn["gaps"]], [("101", d(4))])
        # из двух номеров «меньше 30 %» — только даты, когда не занят ни один: сегодня, завтра, ночь-«окно» и 7-е (12-е закрыто — занято)
        self.assertEqual({x["date"] for x in hn["low_dates"]}, {d(0), d(1), d(4), d(7)})
        self.assertEqual(hn["low_total"], 4)
        # занятая на все номера дата в подсказку не попадает
        self.book(ctx, r1, d(8), d(9))
        hn = self.client.get("/api/today?summary=1", headers=ctx["h"]).json()["summary"]["hints"]
        self.assertNotIn(d(8), [x["date"] for x in hn["low_dates"]])
        # горничной сводки с подсказками не показывают
        r = self.client.post("/api/users", headers=ctx["h"], json={"name": "М", "email": "maid-hint1@example.ru", "role": "housekeeper", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "maid-hint1@example.ru", "password": "password123"}).json()["token"]
        self.assertIsNone(self.client.get("/api/today?summary=1", headers={"Authorization": f"Bearer {tok}"}).json()["summary"])
        self.assertEqual(r.status_code, 200)


class AccountantTests(Base):
    def test_accountant_summary_by_method_and_categories_with_csv(self):
        ctx = self.register("acc1@example.ru")
        b = self.book(ctx, ctx["rooms"][0], d(-3), d(-1), total_price=7000).json()
        pay = lambda amount, method, kind="payment", on=None: self.client.post(f"/api/bookings/{b['id']}/payments", headers=ctx["h"], json={
            "amount": amount, "method": method, "kind": kind, "paid_on": on or d(-2)})
        self.assertEqual(pay(3000, "cash").status_code, 200)
        self.assertEqual(pay(2000, "card").status_code, 200)
        self.assertEqual(pay(500, "cash", "refund").status_code, 200)
        self.assertEqual(pay(1500, "transfer", on=d(-40)).status_code, 200)   # вне периода
        cat = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat["id"], "amount": 1200, "date": d(-2)})
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat["id"], "amount": 800, "date": d(-2)})
        icat = self.client.get("/api/income-categories", headers=ctx["h"]).json()[0]
        self.client.post("/api/incomes", headers=ctx["h"], json={"category_id": icat["id"], "amount": 600, "date": d(-1)})
        r = self.client.get(f"/api/analytics/accountant?from={d(-10)}&to={d(0)}", headers=ctx["h"])
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()
        m = {x["method"]: x for x in a["by_method"]}
        self.assertEqual((float(m["cash"]["payments"]), float(m["cash"]["refunds"]), float(m["cash"]["net"])), (3000.0, 500.0, 2500.0))
        self.assertEqual(float(m["card"]["net"]), 2000.0)
        self.assertNotIn("transfer", m)
        t = a["totals"]
        self.assertEqual((float(t["receipts"]), float(t["other_income"]), float(t["expenses"]), float(t["result"])), (4500.0, 600.0, 2000.0, 3100.0))
        self.assertEqual(float(a["expense_by_category"][0]["amount"]), 2000.0)
        self.assertIn("Налоги не считаются", a["note"])
        csv_r = self.client.get(f"/api/analytics/accountant.csv?from={d(-10)}&to={d(0)}", headers=ctx["h"])
        self.assertEqual(csv_r.status_code, 200)
        self.assertTrue(csv_r.content.startswith("﻿".encode("utf-8")))
        text = csv_r.text
        for needle in ("Поступления по оплатам броней", "Наличные;3000;500;2500".replace(";", ";"), "Реестр платежей", "Возврат", "Итого: поступления"):
            self.assertIn(needle, text.replace("3000,00", "3000").replace("500,00", "500").replace("2500,00", "2500"))
        # другой аккаунт видит пустую сводку
        other = self.register("acc1b@example.ru")
        o = self.client.get(f"/api/analytics/accountant?from={d(-10)}&to={d(0)}", headers=other["h"]).json()
        self.assertEqual(float(o["totals"]["result"]), 0.0)

    def test_csv_formula_injection_is_neutralised(self):
        ctx = self.register("acc2@example.ru")
        b = self.book(ctx, ctx["rooms"][0], d(-3), d(-1), guest="=HYPERLINK(\"http://evil\")", total_price=1000).json()
        self.client.post(f"/api/bookings/{b['id']}/payments", headers=ctx["h"], json={"amount": 100, "method": "cash", "paid_on": d(-2)})
        text = self.client.get(f"/api/analytics/accountant.csv?from={d(-10)}&to={d(0)}", headers=ctx["h"]).text
        self.assertNotIn(";=HYPERLINK", text)
        self.assertIn("'=HYPERLINK", text)


if __name__ == "__main__":
    unittest.main()
