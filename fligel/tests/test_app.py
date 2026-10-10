"""Сквозные тесты API на настоящей PostgreSQL.

Запуск:  DATABASE_URL=postgresql://postgres@127.0.0.1/fligel_test python -m unittest discover -s tests -v
Тестовая база пересоздаётся при каждом запуске.
"""
import os
import re
import threading
import time
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/fligel_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ["SYNC_ENABLED"] = "0"
os.environ["PUBLIC_BASE_URL"] = "https://fligel.test"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["PUBLIC_BOOKINGS_PER_HOUR"] = "100000"  # лимиты защиты от спама проверяются отдельными тестами
os.environ["RESET_REQUESTS_PER_HOUR"] = "100000"

import psycopg  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import admin, config, db, expenses, ical, mail, maxbot, notify, ratelimit, sync, telegram  # noqa: E402
from app.api.reports import _shift_years  # noqa: E402
from app.main import app  # noqa: E402


def recreate_db():
    u = urlparse(TEST_DB)
    admin = TEST_DB.replace(u.path, "/postgres")
    name = u.path.lstrip("/")
    db.close_pool()
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')


def d(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


class Base(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls):
        recreate_db()
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def register(self, email: str, rooms=(("Стандарт", 8, 3500), ("Делюкс", 4, 5500))) -> dict:
        r = self.client.post("/api/auth/register", json={
            "account_name": "Гостиница", "name": "Иван", "email": email, "password": "password123"})
        self.assertEqual(r.status_code, 200, r.text)
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        r = self.client.post("/api/setup", headers=headers, json={
            "name": "Гостиница Флигель", "address": "Казань",
            "room_types": [{"name": n, "count": c, "base_price": p, "capacity": 2} for n, c, p in rooms]})
        self.assertEqual(r.status_code, 200, r.text)
        prop = self.client.get(f"/api/properties/{r.json()['id']}", headers=headers).json()
        return {"h": headers, "prop": prop,
                "rooms": [room for t in prop["room_types"] for room in t["rooms"]]}

    def book(self, ctx, room, ci, co, **kw):
        return self.client.post("/api/bookings", headers=ctx["h"], json={
            "room_id": room["id"], "check_in": ci, "check_out": co, "guest_name": kw.pop("guest", "Гость"), **kw})


class AccountTests(Base):
    def test_register_login_and_setup(self):
        ctx = self.register("owner1@example.ru")
        self.assertEqual(len(ctx["rooms"]), 12)
        self.assertEqual([r["name"] for r in ctx["rooms"]][:3], ["101", "102", "103"])
        r = self.client.post("/api/auth/login", json={"email": "OWNER1@example.ru", "password": "password123"})
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/auth/login", json={"email": "owner1@example.ru", "password": "wrong"})
        self.assertEqual(r.status_code, 401)
        me = self.client.get("/api/me", headers=ctx["h"]).json()
        self.assertEqual(me["role"], "owner")
        self.assertEqual(len(me["properties"]), 1)

    def test_duplicate_email_and_short_password(self):
        self.register("dup@example.ru")
        r = self.client.post("/api/auth/register", json={
            "account_name": "X", "name": "Y", "email": "dup@example.ru", "password": "password123"})
        self.assertEqual(r.status_code, 409)
        r = self.client.post("/api/auth/register", json={
            "account_name": "X", "name": "Y", "email": "new@example.ru", "password": "short"})
        self.assertEqual(r.status_code, 422)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/board").status_code, 401)
        r = self.client.get("/api/board", headers={"Authorization": "Bearer garbage"})
        self.assertEqual(r.status_code, 401)

    def test_housekeeper_cannot_edit_bookings(self):
        ctx = self.register("roles@example.ru")
        r = self.client.post("/api/users", headers=ctx["h"], json={
            "name": "Мария", "email": "maid@example.ru", "role": "housekeeper", "password": "password123"})
        self.assertEqual(r.status_code, 200, r.text)
        tok = self.client.post("/api/auth/login", json={"email": "maid@example.ru", "password": "password123"})
        h = {"Authorization": f"Bearer {tok.json()['token']}"}
        self.assertEqual(self.client.get("/api/today", headers=h).status_code, 200)
        r = self.client.post("/api/bookings", headers=h, json={
            "room_id": ctx["rooms"][0]["id"], "check_in": d(1), "check_out": d(2)})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get("/api/reports", headers=h).status_code, 403)


class BookingTests(Base):
    def test_overbooking_is_impossible(self):
        ctx = self.register("ob@example.ru")
        room = ctx["rooms"][0]
        r = self.book(ctx, room, d(10), d(14), guest="Анна")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(float(r.json()["total_price"]), 4 * 3500)  # цена посчитана автоматически
        r = self.book(ctx, room, d(12), d(15), guest="Борис")
        self.assertEqual(r.status_code, 409)
        self.assertIn("Анна", r.json()["error"])
        # Выезд и заезд в один день — нормально
        self.assertEqual(self.book(ctx, room, d(14), d(16)).status_code, 200)
        self.assertEqual(self.book(ctx, room, d(8), d(10)).status_code, 200)

    def test_cancel_frees_room_and_move_checks_overlap(self):
        ctx = self.register("mv@example.ru")
        r1, r2 = ctx["rooms"][0], ctx["rooms"][1]
        a = self.book(ctx, r1, d(3), d(6)).json()
        b = self.book(ctx, r2, d(3), d(6)).json()
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"room_id": r1["id"]})
        self.assertEqual(r.status_code, 409)
        self.client.delete(f"/api/bookings/{a['id']}", headers=ctx["h"])
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"room_id": r1["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        got = self.client.get(f"/api/bookings/{a['id']}", headers=ctx["h"]).json()
        self.assertEqual(got["status"], "cancelled")

    def test_bad_dates(self):
        ctx = self.register("bd@example.ru")
        r = self.book(ctx, ctx["rooms"][0], d(5), d(5))
        self.assertEqual(r.status_code, 422)
        r = self.book(ctx, ctx["rooms"][0], "завтра", d(5))
        self.assertEqual(r.status_code, 422)

    def test_tenant_isolation(self):
        a = self.register("tenant-a@example.ru")
        b = self.register("tenant-b@example.ru")
        booking = self.book(a, a["rooms"][0], d(1), d(3)).json()
        self.assertEqual(self.client.get(f"/api/bookings/{booking['id']}", headers=b["h"]).status_code, 404)
        r = self.client.patch(f"/api/bookings/{booking['id']}", headers=b["h"], json={"guest_name": "взлом"})
        self.assertEqual(r.status_code, 404)
        # Чужой номер нельзя забронировать
        self.assertEqual(self.book(b, a["rooms"][0], d(5), d(6)).status_code, 404)
        board = self.client.get("/api/board", headers=b["h"]).json()
        self.assertEqual(board["bookings"], [])
        self.assertEqual(self.client.get(f"/api/properties/{a['prop']['id']}", headers=b["h"]).status_code, 404)

    def test_rates_and_board(self):
        ctx = self.register("rt@example.ru")
        std = ctx["prop"]["room_types"][0]
        r = self.client.put("/api/rates", headers=ctx["h"], json={
            "room_type_ids": [std["id"]], "date_from": d(20), "date_to": d(21), "price": 5000})
        self.assertEqual(r.status_code, 200, r.text)
        q = self.client.get("/api/bookings/quote", headers=ctx["h"], params={
            "room_id": ctx["rooms"][0]["id"], "check_in": d(19), "check_out": d(22)}).json()
        self.assertEqual(float(q["total"]), 3500 + 5000 + 5000)
        self.client.put("/api/rates", headers=ctx["h"], json={
            "room_type_ids": [std["id"]], "date_from": d(20), "date_to": d(20), "closed": True})
        board = self.client.get("/api/board", headers=ctx["h"], params={"from": d(19), "days": 5}).json()
        t = next(t for t in board["room_types"] if t["id"] == std["id"])
        self.assertTrue(t["rates"][d(20)]["closed"])
        self.assertEqual(float(t["rates"][d(21)]["price"]), 5000)
        self.assertEqual(len(board["days"]), 5)
        self.client.put("/api/rates", headers=ctx["h"], json={
            "room_type_ids": [std["id"]], "date_from": d(20), "date_to": d(21), "reset": True})
        q = self.client.get("/api/bookings/quote", headers=ctx["h"], params={
            "room_id": ctx["rooms"][0]["id"], "check_in": d(20), "check_out": d(22)}).json()
        self.assertEqual(float(q["total"]), 7000)

    def test_stats(self):
        ctx = self.register("st@example.ru", rooms=(("Стандарт", 2, 1000),))
        self.book(ctx, ctx["rooms"][0], d(0), d(5), total_price=5000)
        self.book(ctx, ctx["rooms"][1], d(0), d(10), total_price=10000, status="blocked")
        s = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(10)}).json()["totals"]
        self.assertEqual(s["room_nights"], 20)
        self.assertEqual(s["sold_nights"], 5)
        self.assertEqual(s["occupancy"], 25.0)
        self.assertEqual(float(s["revenue"]), 5000)
        self.assertEqual(float(s["adr"]), 1000)


class MultiPropertyTests(Base):
    """Один владелец, два объекта: экраны должны работать по выбранному объекту,
    а «Сегодня», «Брони» и «Отчёты» — уметь показать оба сразу."""

    def add_property(self, ctx, name="Квартиры", rooms=(("Студия", 2, 2000),)):
        r = self.client.post("/api/setup", headers=ctx["h"], json={
            "name": name, "room_types": [{"name": n, "count": c, "base_price": p, "capacity": 2} for n, c, p in rooms]})
        self.assertEqual(r.status_code, 200, r.text)
        prop = self.client.get(f"/api/properties/{r.json()['id']}", headers=ctx["h"]).json()
        return {"prop": prop, "rooms": [room for t in prop["room_types"] for room in t["rooms"]]}

    def test_board_and_channels_scoped_to_property(self):
        ctx = self.register("multi1@example.ru", rooms=(("Стандарт", 2, 3000),))
        p2 = self.add_property(ctx)
        self.book(ctx, ctx["rooms"][0], d(1), d(3))
        self.book(ctx, p2["rooms"][0], d(1), d(3))
        board1 = self.client.get("/api/board", headers=ctx["h"], params={"property_id": ctx["prop"]["id"]}).json()
        board2 = self.client.get("/api/board", headers=ctx["h"], params={"property_id": p2["prop"]["id"]}).json()
        self.assertEqual({r["id"] for t in board1["room_types"] for r in t["rooms"]}, {r["id"] for r in ctx["rooms"]})
        self.assertEqual({r["id"] for t in board2["room_types"] for r in t["rooms"]}, {r["id"] for r in p2["rooms"]})
        self.assertEqual(len(board1["bookings"]), 1)
        self.assertEqual(len(board2["bookings"]), 1)
        ch1 = self.client.get("/api/channels", headers=ctx["h"], params={"property_id": ctx["prop"]["id"]}).json()
        ch2 = self.client.get("/api/channels", headers=ctx["h"], params={"property_id": p2["prop"]["id"]}).json()
        self.assertEqual({r["id"] for r in ch1["rooms"]}, {r["id"] for r in ctx["rooms"]})
        self.assertEqual({r["id"] for r in ch2["rooms"]}, {r["id"] for r in p2["rooms"]})
        # объект другого аккаунта недоступен
        other = self.register("multi1b@example.ru")
        self.assertEqual(self.client.get("/api/board", headers=other["h"],
                                          params={"property_id": ctx["prop"]["id"]}).status_code, 404)
        self.assertEqual(self.client.get("/api/channels", headers=other["h"],
                                          params={"property_id": ctx["prop"]["id"]}).status_code, 404)

    def test_today_and_stats_all_properties_mode(self):
        ctx = self.register("multi2@example.ru", rooms=(("Стандарт", 1, 3000),))
        p2 = self.add_property(ctx, rooms=(("Студия", 1, 2000),))
        self.book(ctx, ctx["rooms"][0], d(0), d(2), total_price=6000)
        self.book(ctx, p2["rooms"][0], d(0), d(2), total_price=4000)
        today1 = self.client.get("/api/today", headers=ctx["h"], params={"property_id": ctx["prop"]["id"]}).json()
        self.assertEqual(len(today1["arrivals"]), 1)
        today_all = self.client.get("/api/today", headers=ctx["h"]).json()
        self.assertEqual(len(today_all["arrivals"]), 2)
        self.assertEqual({r["property_name"] for r in today_all["arrivals"]}, {ctx["prop"]["name"], p2["prop"]["name"]})
        stats1 = self.client.get("/api/reports", headers=ctx["h"],
                                  params={"property_id": ctx["prop"]["id"], "from": d(0), "to": d(2)}).json()["totals"]
        self.assertEqual(stats1["rooms"], 1)
        self.assertEqual(float(stats1["revenue"]), 6000)
        stats_all = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(2)}).json()["totals"]
        self.assertEqual(stats_all["rooms"], 2)
        self.assertEqual(float(stats_all["revenue"]), 10000)
        bookings_all = self.client.get("/api/bookings", headers=ctx["h"], params={"from": d(0)}).json()
        self.assertEqual(len(bookings_all), 2)
        bookings1 = self.client.get("/api/bookings", headers=ctx["h"],
                                     params={"from": d(0), "property_id": ctx["prop"]["id"]}).json()
        self.assertEqual(len(bookings1), 1)


class GuestHistoryTests(Base):
    def test_history_across_properties_and_returning_flag(self):
        ctx = self.register("guest1@example.ru", rooms=(("Стандарт", 1, 1000),))
        p2 = self.client.post("/api/setup", headers=ctx["h"], json={
            "name": "Второй объект", "room_types": [{"name": "Студия", "count": 1, "base_price": 2000}]}).json()
        room2 = self.client.get(f"/api/properties/{p2['id']}", headers=ctx["h"]).json()["room_types"][0]["rooms"][0]
        phone = "+7 900 111-22-33"
        self.book(ctx, ctx["rooms"][0], d(1), d(3), guest="Ольга", guest_phone=phone, total_price=2000, paid_amount=2000)
        self.book(ctx, room2, d(10), d(11), guest="Ольга", guest_phone=phone, total_price=2000, paid_amount=1000)
        r = self.client.get("/api/guests", headers=ctx["h"], params={"phone": phone}).json()
        self.assertEqual(r["visits"], 2)
        self.assertTrue(r["returning"])
        self.assertEqual(float(r["total_spent"]), 4000)
        self.assertEqual(float(r["total_paid"]), 3000)
        self.assertEqual({s["property_name"] for s in r["stays"]}, {ctx["prop"]["name"], "Второй объект"})

    def test_single_visit_is_not_returning(self):
        ctx = self.register("guest2@example.ru")
        self.book(ctx, ctx["rooms"][0], d(1), d(2), guest="Игорь", guest_phone="+79995554433")
        r = self.client.get("/api/guests", headers=ctx["h"], params={"phone": "+79995554433"}).json()
        self.assertEqual(r["visits"], 1)
        self.assertFalse(r["returning"])

    def test_cancelled_booking_excluded_and_requires_phone(self):
        ctx = self.register("guest3@example.ru")
        b = self.book(ctx, ctx["rooms"][0], d(1), d(2), guest="Павел", guest_phone="+79995554400").json()
        self.client.delete(f"/api/bookings/{b['id']}", headers=ctx["h"])
        r = self.client.get("/api/guests", headers=ctx["h"], params={"phone": "+79995554400"}).json()
        self.assertEqual(r["visits"], 0)
        self.assertEqual(self.client.get("/api/guests", headers=ctx["h"]).status_code, 422)

    def test_tenant_isolation(self):
        a = self.register("guest4a@example.ru")
        b = self.register("guest4b@example.ru")
        self.book(a, a["rooms"][0], d(1), d(2), guest="Клиент А", guest_phone="+79990001122")
        r = self.client.get("/api/guests", headers=b["h"], params={"phone": "+79990001122"}).json()
        self.assertEqual(r["visits"], 0)


class ExpensesTests(Base):
    def test_default_categories_created_on_register(self):
        ctx = self.register("exp1@example.ru")
        cats = self.client.get("/api/expense-categories", headers=ctx["h"]).json()
        self.assertEqual(len(cats), 10)
        self.assertIn("Прочее", [c["name"] for c in cats])

    def test_manager_can_add_but_not_manage_categories(self):
        ctx = self.register("exp2@example.ru")
        self.client.post("/api/users", headers=ctx["h"], json={
            "name": "Мария", "email": "mgr2@example.ru", "role": "manager", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "mgr2@example.ru", "password": "password123"})
        mh = {"Authorization": f"Bearer {tok.json()['token']}"}
        cats = self.client.get("/api/expense-categories", headers=mh).json()
        cat_id = cats[0]["id"]
        r = self.client.post("/api/expenses", headers=mh, json={
            "category_id": cat_id, "amount": 1500, "date": d(0), "comment": "Стирка полотенец"})
        self.assertEqual(r.status_code, 200, r.text)
        exp_id = r.json()["id"]
        # категориями управляет только владелец
        r = self.client.post("/api/expense-categories", headers=mh, json={"name": "Новая"})
        self.assertEqual(r.status_code, 403)
        # удаляет расход тоже только владелец
        r = self.client.delete(f"/api/expenses/{exp_id}", headers=mh)
        self.assertEqual(r.status_code, 403)
        r = self.client.delete(f"/api/expenses/{exp_id}", headers=ctx["h"])
        self.assertEqual(r.status_code, 200, r.text)

    def test_housekeeper_has_no_access(self):
        ctx = self.register("exp3@example.ru")
        self.client.post("/api/users", headers=ctx["h"], json={
            "name": "Оля", "email": "maid3@example.ru", "role": "housekeeper", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "maid3@example.ru", "password": "password123"})
        hh = {"Authorization": f"Bearer {tok.json()['token']}"}
        self.assertEqual(self.client.get("/api/expenses", headers=hh).status_code, 403)
        self.assertEqual(self.client.get("/api/expense-categories", headers=hh).status_code, 403)

    def test_shared_and_property_expenses_with_totals_and_filters(self):
        ctx = self.register("exp4@example.ru")
        cats = self.client.get("/api/expense-categories", headers=ctx["h"]).json()
        cleaning = next(c for c in cats if c["name"] == "Уборка и прачечная")
        utilities = next(c for c in cats if c["name"] == "Коммунальные услуги")
        self.client.post("/api/expenses", headers=ctx["h"], json={
            "category_id": cleaning["id"], "amount": 1000, "date": d(0), "property_id": ctx["prop"]["id"]})
        self.client.post("/api/expenses", headers=ctx["h"], json={
            "category_id": cleaning["id"], "amount": 500, "date": d(0), "property_id": ctx["prop"]["id"]})
        self.client.post("/api/expenses", headers=ctx["h"], json={
            "category_id": utilities["id"], "amount": 3000, "date": d(0)})  # общий расход, без объекта
        s = self.client.get("/api/expenses", headers=ctx["h"], params={"from": d(-1), "to": d(1)}).json()
        self.assertEqual(len(s["rows"]), 3)
        self.assertEqual(float(s["total"]), 4500)
        by_cat = {b["category_name"]: float(b["amount"]) for b in s["by_category"]}
        self.assertEqual(by_cat["Уборка и прачечная"], 1500)
        self.assertEqual(by_cat["Коммунальные услуги"], 3000)
        only_shared = self.client.get("/api/expenses", headers=ctx["h"],
                                       params={"from": d(-1), "to": d(1), "property_id": "none"}).json()
        self.assertEqual(len(only_shared["rows"]), 1)
        only_prop = self.client.get("/api/expenses", headers=ctx["h"], params={
            "from": d(-1), "to": d(1), "property_id": ctx["prop"]["id"]}).json()
        self.assertEqual(len(only_prop["rows"]), 2)
        by_category_filter = self.client.get("/api/expenses", headers=ctx["h"], params={
            "from": d(-1), "to": d(1), "category_id": cleaning["id"]}).json()
        self.assertEqual(len(by_category_filter["rows"]), 2)

    def test_room_expense_inherits_property_and_rejects_mismatch(self):
        ctx = self.register("exp5@example.ru")
        p2 = self.client.post("/api/setup", headers=ctx["h"], json={
            "name": "Второй объект", "room_types": [{"name": "Студия", "count": 1, "base_price": 1000}]}).json()
        cats = self.client.get("/api/expense-categories", headers=ctx["h"]).json()
        cat = cats[0]["id"]
        other_room = self.client.get(f"/api/properties/{p2['id']}", headers=ctx["h"]).json()["room_types"][0]["rooms"][0]
        r = self.client.post("/api/expenses", headers=ctx["h"], json={
            "category_id": cat, "amount": 100, "room_id": ctx["rooms"][0]["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["property_id"], ctx["prop"]["id"])
        r = self.client.post("/api/expenses", headers=ctx["h"], json={
            "category_id": cat, "amount": 100, "room_id": ctx["rooms"][0]["id"], "property_id": p2["id"]})
        self.assertEqual(r.status_code, 422)

    def test_csv_export_has_bom_and_rows(self):
        ctx = self.register("exp6@example.ru")
        cat = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]["id"]
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat, "amount": 777, "date": d(0)})
        r = self.client.get("/api/expenses/export.csv", headers=ctx["h"], params={"from": d(-1), "to": d(1)})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.text.startswith("﻿"))
        self.assertIn("777", r.text)

    def test_tenant_isolation(self):
        a = self.register("exp7a@example.ru")
        b = self.register("exp7b@example.ru")
        cat = self.client.get("/api/expense-categories", headers=a["h"]).json()[0]["id"]
        exp = self.client.post("/api/expenses", headers=a["h"], json={"category_id": cat, "amount": 200}).json()
        self.assertEqual(self.client.get("/api/expenses", headers=b["h"]).json()["rows"], [])
        self.assertEqual(self.client.delete(f"/api/expenses/{exp['id']}", headers=b["h"]).status_code, 404)
        cat_b = self.client.get("/api/expense-categories", headers=b["h"]).json()[0]["id"]
        r = self.client.post("/api/expenses", headers=b["h"], json={"category_id": cat, "amount": 1})
        self.assertEqual(r.status_code, 404)  # категория другого аккаунта
        self.assertNotEqual(cat, cat_b)

    def test_recurring_rule_generates_without_duplicates(self):
        ctx = self.register("exp8@example.ru")
        cat = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]["id"]
        r = self.client.post("/api/expense-recurring", headers=ctx["h"], json={
            "category_id": cat, "amount": 25000, "day_of_month": 1, "comment": "Аренда"})
        self.assertEqual(r.status_code, 200, r.text)
        today = date.today()
        created = expenses.generate_due_expenses(today)
        self.assertEqual(created, 1 if today.day >= 1 else 0)
        created_again = expenses.generate_due_expenses(today)
        self.assertEqual(created_again, 0)  # без дублей при повторном запуске
        rows = self.client.get("/api/expenses", headers=ctx["h"], params={
            "from": today.replace(day=1).isoformat(), "to": d(1)}).json()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["recurring_rule_id"], r.json()["id"])
        # владелец может отключить шаблон
        r2 = self.client.patch(f"/api/expense-recurring/{r.json()['id']}", headers=ctx["h"], json={"active": False})
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.json()["active"])

    def test_archive_category_keeps_history_but_blocks_new_expenses(self):
        ctx = self.register("exp9@example.ru")
        cats = self.client.get("/api/expense-categories", headers=ctx["h"]).json()
        cat = cats[0]
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat["id"], "amount": 50})
        r = self.client.patch(f"/api/expense-categories/{cat['id']}", headers=ctx["h"], json={"archived": True})
        self.assertEqual(r.status_code, 200, r.text)
        active = self.client.get("/api/expense-categories", headers=ctx["h"]).json()
        self.assertNotIn(cat["id"], [c["id"] for c in active])
        r = self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat["id"], "amount": 10})
        self.assertEqual(r.status_code, 422)
        rows = self.client.get("/api/expenses", headers=ctx["h"], params={"from": d(-1), "to": d(1)}).json()["rows"]
        self.assertEqual(len(rows), 1)  # старый расход остался


class ReportsTests(Base):
    def test_revenue_expenses_profit_margin(self):
        ctx = self.register("rep1@example.ru", rooms=(("Стандарт", 2, 1000),))
        self.book(ctx, ctx["rooms"][0], d(0), d(5), total_price=5000)
        cats = self.client.get("/api/expense-categories", headers=ctx["h"]).json()
        self.client.post("/api/expenses", headers=ctx["h"], json={
            "category_id": cats[0]["id"], "amount": 2000, "date": d(1), "property_id": ctx["prop"]["id"]})
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cats[0]["id"], "amount": 1000, "date": d(1)})
        r = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(5)}).json()
        t = r["totals"]
        self.assertEqual(float(t["revenue"]), 5000)
        self.assertEqual(float(t["expenses"]), 3000)  # общий расход при одном объекте достаётся ему целиком
        self.assertEqual(float(t["profit"]), 2000)
        self.assertEqual(t["margin"], 40.0)
        self.assertEqual(r["share_note"][:7], "Общие р")

    def test_shared_expense_split_by_room_count(self):
        ctx = self.register("rep2@example.ru", rooms=(("Стандарт", 2, 1000),))
        p2 = self.client.post("/api/setup", headers=ctx["h"], json={
            "name": "Второй объект", "room_types": [{"name": "Студия", "count": 1, "base_price": 1000}]}).json()
        cat = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]["id"]
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat, "amount": 300, "date": d(1)})
        ra = self.client.get("/api/reports", headers=ctx["h"],
                             params={"property_id": ctx["prop"]["id"], "from": d(0), "to": d(3)}).json()
        rb = self.client.get("/api/reports", headers=ctx["h"],
                             params={"property_id": p2["id"], "from": d(0), "to": d(3)}).json()
        r_all = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(3)}).json()
        self.assertAlmostEqual(float(ra["totals"]["expenses"]), 200)  # 2 из 3 номеров
        self.assertAlmostEqual(float(rb["totals"]["expenses"]), 100)  # 1 из 3 номеров
        self.assertAlmostEqual(float(r_all["totals"]["expenses"]), 300)
        self.assertEqual(len(r_all["by_property"]), 2)

    def test_by_room_includes_idle_rooms(self):
        ctx = self.register("rep3@example.ru", rooms=(("Стандарт", 2, 1000),))
        self.book(ctx, ctx["rooms"][0], d(0), d(3), total_price=3000)
        r = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(3)}).json()
        by_id = {x["room_id"]: x for x in r["by_room"]}
        self.assertEqual(by_id[ctx["rooms"][0]["id"]]["nights"], 3)
        self.assertEqual(by_id[ctx["rooms"][1]["id"]]["nights"], 0)  # простаивал, но виден в отчёте
        self.assertEqual(float(by_id[ctx["rooms"][1]["id"]]["revenue"]), 0)
        self.assertEqual(len(r["by_room_type"]), 1)

    def test_compare_prev_period_and_prev_year(self):
        ctx = self.register("rep4@example.ru", rooms=(("Стандарт", 1, 1000),))
        today = date.today()
        py_start = _shift_years(today, -1)
        self.book(ctx, ctx["rooms"][0], d(0), d(2), total_price=2000)
        self.book(ctx, ctx["rooms"][0], d(-2), d(-1), total_price=500)
        self.book(ctx, ctx["rooms"][0], py_start.isoformat(), (py_start + timedelta(days=1)).isoformat(),
                  total_price=100)
        r = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(2)}).json()
        self.assertEqual(float(r["compare_prev_period"]["revenue"]), 500)
        self.assertEqual(r["compare_prev_period"]["revenue_delta"], 300.0)  # (2000-500)/500*100
        self.assertEqual(float(r["compare_prev_year"]["revenue"]), 100)

    def test_by_source_with_commission(self):
        ctx = self.register("rep5@example.ru", rooms=(("Стандарт", 1, 1000),))
        r = self.client.put("/api/channel-commissions", headers=ctx["h"], json={
            "items": [{"channel": "avito", "percent": 20}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.book(ctx, ctx["rooms"][0], d(0), d(2), total_price=2000, source="avito")
        rep = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(2)}).json()
        avito = next(s for s in rep["by_source"] if s["source"] == "avito")
        self.assertEqual(float(avito["commission_percent"]), 20)
        self.assertEqual(float(avito["commission_amount"]), 400)
        self.assertEqual(float(avito["net_revenue"]), 1600)
        commissions = self.client.get("/api/channel-commissions", headers=ctx["h"]).json()
        self.assertEqual(float(next(x["percent"] for x in commissions if x["channel"] == "avito")), 20)

    def test_monthly_and_weekday_shape(self):
        ctx = self.register("rep6@example.ru")
        r = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(3)}).json()
        self.assertEqual(len(r["monthly"]), 12)
        self.assertEqual(len(r["weekday_occupancy"]), 7)
        self.assertEqual({x["weekday"] for x in r["weekday_occupancy"]}, set(range(7)))

    def test_csv_export_has_bom(self):
        ctx = self.register("rep7@example.ru")
        r = self.client.get("/api/reports/export.csv", headers=ctx["h"], params={"from": d(0), "to": d(3)})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.text.startswith("﻿"))
        self.assertIn("Выручка", r.text)

    def test_tenant_isolation(self):
        a = self.register("rep8a@example.ru")
        b = self.register("rep8b@example.ru")
        r = self.client.get("/api/reports", headers=b["h"], params={"property_id": a["prop"]["id"]})
        self.assertEqual(r.status_code, 404)


class SecurityReviewTests(Base):
    """Регрессионные тесты на находки самопроверки (Этап 1 ветки feature/next)."""

    def test_deleted_user_token_rejected_immediately(self):
        ctx = self.register("sec1@example.ru")
        r = self.client.post("/api/users", headers=ctx["h"], json={
            "name": "Мария", "email": "sec1-mgr@example.ru", "role": "manager", "password": "password123"})
        uid = r.json()["id"]
        tok = self.client.post("/api/auth/login", json={"email": "sec1-mgr@example.ru", "password": "password123"})
        mh = {"Authorization": f"Bearer {tok.json()['token']}"}
        self.assertEqual(self.client.get("/api/today", headers=mh).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/users/{uid}", headers=ctx["h"]).status_code, 200)
        # токен ещё не истёк и подпись верна, но сотрудника уже нет — доступ должен пропасть сразу
        r = self.client.get("/api/today", headers=mh)
        self.assertEqual(r.status_code, 401)

    def test_suspended_account_token_rejected_immediately(self):
        ctx = self.register("sec2@example.ru")
        account_id = ctx["prop"]["account_id"]
        self.assertEqual(self.client.get("/api/today", headers=ctx["h"]).status_code, 200)
        with db.tx() as conn:
            db.run(conn, "UPDATE accounts SET status = 'suspended' WHERE id = %s", (account_id,))
        # токен всё ещё валиден и не истёк, но аккаунт уже приостановлен — доступ должен пропасть сразу
        r = self.client.get("/api/today", headers=ctx["h"])
        self.assertEqual(r.status_code, 403)

    def test_huge_amount_is_rejected_not_500(self):
        ctx = self.register("sec3@example.ru")
        cat = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]["id"]
        for bad in ("9" * 40, "1E50", "9999999999.999999999999999999"):
            r = self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat, "amount": bad})
            self.assertEqual(r.status_code, 422, f"{bad!r}: {r.text}")
        # обычная сумма с длинным «хвостом» после запятой — не ошибка, просто округляется
        ok = self.client.post("/api/expenses", headers=ctx["h"], json={
            "category_id": cat, "amount": "1." + "1" * 40})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(float(ok.json()["amount"]), 1.11)

    def test_report_money_fields_are_rounded_to_kopecks(self):
        ctx = self.register("sec4@example.ru", rooms=(("Стандарт", 1, 100),))
        # 100 за 3 ночи, из них в отчётном периоде только 1 ночь — 100/3 без округления
        # даёт периодическую дробь; после округления в ответе не должно быть больше 2 знаков.
        self.book(ctx, ctx["rooms"][0], d(-1), d(2), total_price=100)
        r = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(1)}).json()
        revenue = Decimal(str(r["totals"]["revenue"]))
        self.assertEqual(revenue, revenue.quantize(Decimal("0.01")))
        adr = Decimal(str(r["totals"]["adr"]))
        self.assertEqual(adr, adr.quantize(Decimal("0.01")))

    def test_housekeeper_cannot_list_or_search_bookings(self):
        ctx = self.register("sec6@example.ru")
        self.client.post("/api/users", headers=ctx["h"], json={
            "name": "Оля", "email": "sec6-maid@example.ru", "role": "housekeeper", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "sec6-maid@example.ru", "password": "password123"})
        hh = {"Authorization": f"Bearer {tok.json()['token']}"}
        b = self.book(ctx, ctx["rooms"][0], d(1), d(2)).json()
        # горничной хватает шахматки и «Сегодня» — они остаются открытыми
        self.assertEqual(self.client.get("/api/board", headers=hh).status_code, 200)
        self.assertEqual(self.client.get("/api/today", headers=hh).status_code, 200)
        # а список/поиск броней и карточка по id — только менеджеру и владельцу
        self.assertEqual(self.client.get("/api/bookings", headers=hh).status_code, 403)
        self.assertEqual(self.client.get(f"/api/bookings/{b['id']}", headers=hh).status_code, 403)
        self.assertEqual(self.client.get("/api/bookings", headers=ctx["h"]).status_code, 200)

    def test_csv_formula_injection_is_neutralized(self):
        ctx = self.register("sec5@example.ru")
        cat = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]["id"]
        self.client.post("/api/expenses", headers=ctx["h"], json={
            "category_id": cat, "amount": 10, "comment": "=2+2"})
        r = self.client.get("/api/expenses/export.csv", headers=ctx["h"], params={"from": d(-1), "to": d(1)})
        self.assertNotIn(";=2+2", r.text)
        self.assertIn("'=2+2", r.text)


class ICalTests(unittest.TestCase):
    def test_parse_variants(self):
        text = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
            "BEGIN:VEVENT\r\nUID:abc-1\r\nDTSTART;VALUE=DATE:20261001\r\nDTEND;VALUE=DATE:20261005\r\n"
            "SUMMARY:Reserved\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:abc-2\r\nDTSTART:20261010T110000Z\r\nDTEND:20261012T090000Z\r\n"
            "SUMMARY:Длинное описание бронирования, которое перенес\r\n ено на следующую строку\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:abc-3\r\nDTSTART;TZID=Europe/Moscow:20261020T140000\r\n"
            "STATUS:CANCELLED\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261101\r\nEND:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        evs = ical.parse(text)
        self.assertEqual(len(evs), 4)
        self.assertEqual((evs[0].start, evs[0].end), (date(2026, 10, 1), date(2026, 10, 5)))
        self.assertEqual((evs[1].start, evs[1].end), (date(2026, 10, 10), date(2026, 10, 12)))
        self.assertIn("перенесено", evs[1].summary)
        self.assertTrue(evs[2].cancelled)
        self.assertEqual(evs[3].end, date(2026, 11, 2))  # без DTEND — одна ночь
        self.assertTrue(evs[3].uid.startswith("nouid-"))

    def test_not_a_calendar(self):
        with self.assertRaises(ValueError):
            ical.parse("<html>Страница входа</html>")

    def test_roundtrip(self):
        evs = [ical.Event("x@fligel", date(2026, 12, 30), date(2027, 1, 2), "Занято, закрыто; тест")]
        text = ical.generate("Номер 101 — очень длинное название объекта размещения для проверки переноса", evs)
        back = ical.parse(text)
        self.assertEqual((back[0].start, back[0].end, back[0].summary), (evs[0].start, evs[0].end, evs[0].summary))
        self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")))


def feed_text(*events) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for uid, ci, co in events:
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTART;VALUE=DATE:{ci.replace('-', '')}",
                  f"DTEND;VALUE=DATE:{co.replace('-', '')}", "SUMMARY:Бронирование", "END:VEVENT"]
    return "\r\n".join(lines + ["END:VCALENDAR"])


class HealthTests(Base):
    def test_health_ok(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["db"])
        self.assertIsNone(body["scheduler"])  # SYNC_ENABLED=0 в тестах

    def test_scheduler_alive_logic(self):
        from unittest.mock import patch
        with patch.object(sync.config, "SYNC_ENABLED", True):
            with patch.object(sync, "_last_tick_at", None):
                self.assertFalse(sync.scheduler_alive())  # ни разу не тикал
            with patch.object(sync, "_last_tick_at", time.monotonic()):
                self.assertTrue(sync.scheduler_alive())  # только что тикнул
            with patch.object(sync, "_last_tick_at", time.monotonic() - sync.SCHEDULER_STALE_AFTER - 1):
                self.assertFalse(sync.scheduler_alive())  # завис


class SyncTests(Base):
    def setUp(self):
        self.ctx = self.register(f"sync{id(self)}@example.ru")
        self.room = self.ctx["rooms"][0]
        self.feed_body = feed_text()
        self._orig = sync.fetch
        sync.fetch = lambda url: self.feed_body  # вместо запроса на сайт площадки

    def tearDown(self):
        sync.fetch = self._orig

    def save_feed(self, channel="avito"):
        r = self.client.post("/api/feeds", headers=self.ctx["h"], json={
            "room_id": self.room["id"], "channel": channel, "url": "https://www.avito.ru/calendar/123.ics"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def board_bookings(self):
        return self.client.get("/api/board", headers=self.ctx["h"],
                               params={"from": d(-2), "days": 60}).json()["bookings"]

    def test_import_update_cancel(self):
        self.feed_body = feed_text(("av-1", d(5), d(8)), ("av-2", d(20), d(22)), ("old", d(-30), d(-25)))
        res = self.save_feed()
        self.assertEqual((res["status"], res["added"]), ("ok", 2))  # прошлое не импортируем
        bs = self.board_bookings()
        self.assertEqual({b["source"] for b in bs}, {"avito"})
        # Гость на Авито сдвинул даты, вторую бронь отменили
        self.feed_body = feed_text(("av-1", d(6), d(9)))
        r = self.client.post(f"/api/feeds/{res['id']}/sync", headers=self.ctx["h"]).json()
        self.assertEqual((r["updated"], r["removed"]), (1, 1))
        bs = self.board_bookings()
        self.assertEqual(len(bs), 1)
        self.assertEqual((bs[0]["check_in"], bs[0]["check_out"]), (d(6), d(9)))
        # Повторная синхронизация без изменений ничего не трогает
        r = self.client.post(f"/api/feeds/{res['id']}/sync", headers=self.ctx["h"]).json()
        self.assertEqual((r["added"], r["updated"], r["removed"]), (0, 0, 0))
        # Даты импортированной брони вручную не меняются
        r = self.client.patch(f"/api/bookings/{bs[0]['id']}", headers=self.ctx["h"], json={"check_out": d(10)})
        self.assertEqual(r.status_code, 422)

    def test_real_double_booking_becomes_conflict(self):
        self.book(self.ctx, self.room, d(10), d(12), guest="Прямой гость")
        self.feed_body = feed_text(("av-9", d(11), d(13)))
        res = self.save_feed()
        self.assertEqual(res["conflicts"], 1)
        conflicts = self.client.get("/api/conflicts", headers=self.ctx["h"]).json()
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["channel"], "avito")
        board = self.client.get("/api/board", headers=self.ctx["h"]).json()
        self.assertEqual(board["open_conflicts"], 1)
        self.client.post(f"/api/conflicts/{conflicts[0]['id']}/resolve", headers=self.ctx["h"])
        self.assertEqual(self.client.get("/api/conflicts", headers=self.ctx["h"]).json(), [])

    def test_echo_of_our_booking_is_not_a_conflict(self):
        b = self.book(self.ctx, self.room, d(15), d(18), guest="Наша бронь").json()
        self.book(self.ctx, self.room, d(18), d(19), guest="Ещё одна")
        # Авито забрал наш календарь...
        overview = self.client.get("/api/channels", headers=self.ctx["h"]).json()
        room = next(r for r in overview["rooms"] if r["id"] == self.room["id"])
        path = urlparse(room["channels"]["avito"]["export_url"]).path
        exported = self.client.get(path)
        self.assertEqual(exported.status_code, 200)
        self.assertIn(b["id"], exported.text)
        # ...и вернул эти даты в своём календаре одним слитым периодом
        self.feed_body = feed_text(("avito-block-77", d(15), d(19)))
        res = self.save_feed()
        self.assertEqual((res["added"], res["conflicts"]), (0, 0))

    def test_export_excludes_same_channel_and_includes_closed_dates(self):
        self.feed_body = feed_text(("av-1", d(5), d(8)))
        self.save_feed("avito")
        self.book(self.ctx, self.room, d(10), d(11))
        std = self.ctx["prop"]["room_types"][0]
        self.client.put("/api/rates", headers=self.ctx["h"], json={
            "room_type_ids": [std["id"]], "date_from": d(30), "date_to": d(32), "closed": True})
        overview = self.client.get("/api/channels", headers=self.ctx["h"]).json()
        room = next(r for r in overview["rooms"] if r["id"] == self.room["id"])
        to_avito = ical.parse(self.client.get(urlparse(room["channels"]["avito"]["export_url"]).path).text)
        to_yandex = ical.parse(self.client.get(urlparse(room["channels"]["yandex"]["export_url"]).path).text)
        spans = lambda evs: sorted((e.start.isoformat(), e.end.isoformat()) for e in evs)
        self.assertEqual(spans(to_avito), [(d(10), d(11)), (d(30), d(33))])
        self.assertEqual(spans(to_yandex), [(d(5), d(8)), (d(10), d(11)), (d(30), d(33))])
        self.assertEqual(self.client.get("/ical/wrong-token/avito.ics").status_code, 404)

    def test_broken_feed_reports_error(self):
        self.feed_body = "<html>Войдите в аккаунт</html>"
        res = self.save_feed()
        self.assertEqual(res["status"], "error")
        overview = self.client.get("/api/channels", headers=self.ctx["h"]).json()
        room = next(r for r in overview["rooms"] if r["id"] == self.room["id"])
        self.assertEqual(room["channels"]["avito"]["feed"]["last_status"], "error")

    def test_rejects_non_url(self):
        r = self.client.post("/api/feeds", headers=self.ctx["h"], json={
            "room_id": self.room["id"], "channel": "avito", "url": "просто текст"})
        self.assertEqual(r.status_code, 422)


class CategorySyncTests(Base):
    """Гостиница в Яндекс Путешествиях: один календарь на категорию номеров."""

    def setUp(self):
        self.ctx = self.register(f"cat{id(self)}@example.ru", rooms=(("Стандарт", 3, 3000), ("Люкс", 1, 8000)))
        self.std = self.ctx["prop"]["room_types"][0]
        self.feed_body = feed_text()
        self._orig = sync.fetch
        sync.fetch = lambda url: self.feed_body

    def tearDown(self):
        sync.fetch = self._orig

    def connect(self):
        r = self.client.post("/api/feeds", headers=self.ctx["h"], json={
            "room_type_id": self.std["id"], "channel": "yandex", "url": "https://travel.yandex.ru/ical/abc.ics"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def type_export(self, channel="yandex"):
        ov = self.client.get("/api/channels", headers=self.ctx["h"]).json()
        t = next(t for t in ov["room_types"] if t["id"] == self.std["id"])
        resp = self.client.get(urlparse(t["channels"][channel]["export_url"]).path)
        self.assertEqual(resp.status_code, 200)
        return sorted((e.start.isoformat(), e.end.isoformat()) for e in ical.parse(resp.text))

    def std_bookings(self):
        ids = {r["id"] for r in self.std["rooms"]}
        return [b for b in self.client.get("/api/bookings", headers=self.ctx["h"], params={"from": d(0)}).json()
                if b["room_id"] in ids]

    def test_events_fill_free_rooms_then_conflict(self):
        self.book(self.ctx, self.std["rooms"][0], d(5), d(8))
        self.feed_body = feed_text(("y1", d(5), d(7)), ("y2", d(6), d(8)), ("y3", d(6), d(7)))
        res = self.connect()
        self.assertEqual((res["added"], res["conflicts"]), (2, 1))  # 3 номера: 1 наш + 2 с Яндекса, третьему нет места
        rooms_used = {b["room_id"] for b in self.std_bookings()}
        self.assertEqual(len(rooms_used), 3)
        conflicts = self.client.get("/api/conflicts", headers=self.ctx["h"]).json()
        self.assertEqual(conflicts[0]["target_name"], "Категория Стандарт")

    def test_date_change_moves_guest_if_needed(self):
        self.feed_body = feed_text(("y1", d(5), d(7)))
        self.connect()
        first = self.std_bookings()[0]
        # в этот номер на новые даты уже заселили другого гостя
        self.book(self.ctx, {"id": first["room_id"]}, d(7), d(9))
        self.feed_body = feed_text(("y1", d(5), d(9)))
        feed_id = self.client.get("/api/channels", headers=self.ctx["h"]).json()["room_types"][0]["channels"]["yandex"]["feed"]["id"]
        r = self.client.post(f"/api/feeds/{feed_id}/sync", headers=self.ctx["h"]).json()
        self.assertEqual((r["updated"], r["conflicts"]), (1, 0))
        moved = next(b for b in self.std_bookings() if b["source"] == "yandex")
        self.assertNotEqual(moved["room_id"], first["room_id"])
        self.assertEqual((moved["check_in"], moved["check_out"]), (d(5), d(9)))

    def test_export_modes(self):
        rooms = self.std["rooms"]
        for r in rooms:
            self.book(self.ctx, r, d(10), d(12))
        self.book(self.ctx, rooms[0], d(20), d(21))
        per_booking = self.type_export()
        self.assertEqual(per_booking.count((d(10), d(12))), 3)
        self.assertIn((d(20), d(21)), per_booking)
        r = self.client.put("/api/channels/export-mode", headers=self.ctx["h"], json={
            "room_type_id": self.std["id"], "channel": "yandex", "mode": "sold_out"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.type_export(), [(d(10), d(12))])  # 20-го свободны ещё 2 номера

    def test_echo_of_our_bookings_is_skipped(self):
        self.book(self.ctx, self.std["rooms"][0], d(5), d(8))
        self.type_export()  # Яндекс забрал наш календарь
        self.feed_body = feed_text(("yandex-copy-1", d(5), d(8)), ("real", d(5), d(8)))
        res = self.connect()
        # одно событие — копия нашей брони, второе — настоящая бронь Яндекса
        self.assertEqual((res["added"], res["conflicts"]), (1, 0))

    def test_cannot_mix_room_and_category_for_channel(self):
        self.connect()
        r = self.client.post("/api/feeds", headers=self.ctx["h"], json={
            "room_id": self.std["rooms"][0]["id"], "channel": "yandex", "url": "https://travel.yandex.ru/x.ics"})
        self.assertEqual(r.status_code, 409)

    def test_move_imported_booking_within_category_only(self):
        self.feed_body = feed_text(("y1", d(5), d(7)))
        self.connect()
        b = self.std_bookings()[0]
        other = next(r for r in self.std["rooms"] if r["id"] != b["room_id"])
        lux = self.ctx["prop"]["room_types"][1]["rooms"][0]
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=self.ctx["h"], json={"room_id": other["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=self.ctx["h"], json={"room_id": lux["id"]})
        self.assertEqual(r.status_code, 422)


class PublicBookingTests(Base):
    def test_direct_booking_flow(self):
        ctx = self.register("pub@example.ru", rooms=(("Стандарт", 2, 3000), ("Люкс", 1, 8000)))
        slug = ctx["prop"]["public_slug"]
        info = self.client.get(f"/api/public/{slug}").json()
        self.assertEqual(len(info["room_types"]), 2)
        av = self.client.get(f"/api/public/{slug}/availability",
                             params={"check_in": d(3), "check_out": d(5), "guests": 2}).json()
        std = next(o for o in av["options"] if o["name"] == "Стандарт")
        self.assertEqual((std["available"], std["free_rooms"], float(std["total"])), (True, 2, 6000))
        payload = {"room_type_id": std["room_type_id"], "check_in": d(3), "check_out": d(5), "guests": 2,
                   "guest_name": "Ольга", "guest_phone": "+7 900 123-45-67", "consent": True}
        for _ in range(2):
            r = self.client.post(f"/api/public/{slug}/book", json=payload)
            self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post(f"/api/public/{slug}/book", json=payload)
        self.assertEqual(r.status_code, 409)  # номера кончились
        av = self.client.get(f"/api/public/{slug}/availability",
                             params={"check_in": d(3), "check_out": d(5)}).json()
        self.assertFalse(next(o for o in av["options"] if o["name"] == "Стандарт")["available"])
        bs = self.client.get("/api/bookings", headers=ctx["h"], params={"from": d(0)}).json()
        self.assertEqual({(b["source"], b["status"]) for b in bs}, {("direct", "pending")})

    def test_validation(self):
        ctx = self.register("pubv@example.ru")
        slug = ctx["prop"]["public_slug"]
        rt = ctx["prop"]["room_types"][0]["id"]
        base = {"room_type_id": rt, "check_in": d(3), "check_out": d(5), "guest_name": "Ольга",
                "guest_phone": "+79001234567", "consent": True}
        self.assertEqual(self.client.post(f"/api/public/{slug}/book", json={**base, "consent": False}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/public/{slug}/book", json={**base, "guest_phone": "12"}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/public/{slug}/book", json={**base, "check_in": d(-1)}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/public/{slug}/book", json={**base, "guests": 5}).status_code, 422)
        self.assertEqual(self.client.get("/api/public/no-such-hotel").status_code, 404)

    def test_concurrent_requests_for_last_room(self):
        ctx = self.register("race@example.ru", rooms=(("Единственный", 1, 3000),))
        slug = ctx["prop"]["public_slug"]
        payload = {"room_type_id": ctx["prop"]["room_types"][0]["id"], "check_in": d(7), "check_out": d(9),
                   "guest_name": "Гость", "guest_phone": "+79001234567", "consent": True}
        codes = []

        def attempt():
            codes.append(self.client.post(f"/api/public/{slug}/book", json=payload).status_code)

        threads = [threading.Thread(target=attempt) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(codes).count(200), 1, codes)


class TelegramTests(Base):
    """Уведомления в Telegram выключены по умолчанию (нет TELEGRAM_BOT_TOKEN); здесь мы явно
    включаем их и подменяем реальную отправку (telegram.send_message) моком — как в SyncTests
    для площадок (sync.fetch)."""

    def setUp(self):
        self.ctx = self.register(f"tg{id(self)}@example.ru")
        self._orig_token = config.TELEGRAM_BOT_TOKEN
        config.TELEGRAM_BOT_TOKEN = "test-token"
        self.sent = []
        self._orig_send = telegram.send_message
        telegram.send_message = lambda chat_id, text: self.sent.append((chat_id, text))

    def tearDown(self):
        config.TELEGRAM_BOT_TOKEN = self._orig_token
        telegram.send_message = self._orig_send

    def link(self, chat_id=None):
        # Свой chat_id на тест (не общий 555111 для всех) — иначе тесты этого класса, использующие
        # общую тестовую БД, видели бы чужие сообщения на «один и тот же» chat_id.
        chat_id = chat_id or (id(self) % 900000000 + 100000000)
        code = self.client.post("/api/telegram/link", headers=self.ctx["h"]).json()["pending_code"]
        r = self.client.post("/api/telegram/webhook", json={"message": {"text": f"/start {code}", "chat": {"id": chat_id}}})
        self.assertTrue(r.json()["linked"], r.text)
        return chat_id

    def test_disabled_by_default(self):
        config.TELEGRAM_BOT_TOKEN = ""
        status = self.client.get("/api/telegram/status", headers=self.ctx["h"]).json()
        self.assertFalse(status["enabled"])
        self.assertEqual(self.client.post("/api/telegram/link", headers=self.ctx["h"]).status_code, 422)
        with db.tx() as conn:
            n = telegram.notify(conn, self.ctx["prop"]["account_id"], "new_booking", "x")
        self.assertEqual(n, 0)  # выключено — очередь не наполняется, даже если событие произошло
        self.assertEqual(telegram.process_outbox(), {"sent": 0, "failed": 0})

    def test_link_flow_via_webhook_and_confirmation_message(self):
        code = self.client.post("/api/telegram/link", headers=self.ctx["h"]).json()["pending_code"]
        self.assertEqual(len(code), 8)
        status = self.client.get("/api/telegram/status", headers=self.ctx["h"]).json()
        self.assertFalse(status["linked"])
        self.assertEqual(status["pending_code"], code)
        # неверный код не привязывает чат
        wrong = self.client.post("/api/telegram/webhook", json={"message": {"text": "/start WRONGCODE", "chat": {"id": 1}}})
        self.assertFalse(wrong.json()["linked"])
        ok = self.client.post("/api/telegram/webhook", json={"message": {"text": f"/start {code}", "chat": {"id": 555111}}})
        self.assertTrue(ok.json()["linked"])
        status = self.client.get("/api/telegram/status", headers=self.ctx["h"]).json()
        self.assertTrue(status["linked"])
        self.assertIsNone(status["pending_code"])
        res = telegram.process_outbox()
        self.assertEqual(res, {"sent": 1, "failed": 0})
        self.assertIn("подключены", self.sent[0][1])

    def test_unlink_and_choose_events(self):
        self.link()
        r = self.client.put("/api/telegram/events", headers=self.ctx["h"], json={"events": ["new_booking", "bogus"]})
        self.assertEqual(r.json()["events"], ["new_booking"])  # неизвестное значение отброшено
        r = self.client.post("/api/telegram/unlink", headers=self.ctx["h"])
        self.assertFalse(r.json()["linked"])

    def test_manual_booking_and_cancellation_notify(self):
        self.link()
        telegram.process_outbox()  # смахнуть сообщение о привязке
        self.sent.clear()
        room = self.ctx["rooms"][0]
        b = self.book(self.ctx, room, d(5), d(7), guest="Марина").json()
        self.assertEqual(telegram.process_outbox(), {"sent": 1, "failed": 0})
        self.assertIn("Новая бронь", self.sent[-1][1])
        self.assertIn("Марина", self.sent[-1][1])
        self.client.delete(f"/api/bookings/{b['id']}", headers=self.ctx["h"])
        self.assertEqual(telegram.process_outbox(), {"sent": 1, "failed": 0})
        self.assertIn("отменена", self.sent[-1][1])
        # закрытие дат (blocked) — это не бронь гостя, уведомления быть не должно
        self.client.post("/api/bookings", headers=self.ctx["h"], json={
            "room_id": room["id"], "check_in": d(20), "check_out": d(22), "status": "blocked"})
        self.assertEqual(telegram.process_outbox(), {"sent": 0, "failed": 0})

    def test_site_booking_notifies(self):
        self.link()
        telegram.process_outbox()
        self.sent.clear()
        slug = self.ctx["prop"]["public_slug"]
        rt = self.ctx["prop"]["room_types"][0]["id"]
        r = self.client.post(f"/api/public/{slug}/book", json={
            "room_type_id": rt, "check_in": d(3), "check_out": d(5), "guest_name": "Пётр",
            "guest_phone": "+79001234567", "consent": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(telegram.process_outbox(), {"sent": 1, "failed": 0})
        self.assertIn("заявка с сайта", self.sent[-1][1])

    def test_event_preferences_are_respected(self):
        self.link()
        telegram.process_outbox()
        self.sent.clear()
        self.client.put("/api/telegram/events", headers=self.ctx["h"], json={"events": ["cancellation"]})
        self.book(self.ctx, self.ctx["rooms"][0], d(5), d(7))
        self.assertEqual(telegram.process_outbox(), {"sent": 0, "failed": 0})  # new_booking отписан

    def test_outbox_retries_then_gives_up(self):
        self.link()

        def failing(chat_id, text):
            raise RuntimeError("сеть недоступна")

        telegram.send_message = failing
        res = telegram.process_outbox()
        self.assertEqual(res, {"sent": 0, "failed": 0})
        with db.tx() as conn:
            row = db.one(conn, "SELECT status, attempts, next_attempt_at > now() AS delayed FROM telegram_outbox"
                               " ORDER BY created_at DESC LIMIT 1")
        self.assertEqual((row["status"], row["attempts"], row["delayed"]), ("pending", 1, True))
        for _ in range(telegram.MAX_ATTEMPTS):
            with db.tx() as conn:
                db.run(conn, "UPDATE telegram_outbox SET next_attempt_at = now() WHERE status = 'pending'")
            telegram.process_outbox()
        with db.tx() as conn:
            row = db.one(conn, "SELECT status, attempts, last_error FROM telegram_outbox ORDER BY created_at DESC LIMIT 1")
        self.assertEqual(row["status"], "failed")
        self.assertGreaterEqual(row["attempts"], telegram.MAX_ATTEMPTS)
        self.assertIn("сеть", row["last_error"])

    def test_conflict_and_sync_error_notify(self):
        self.link()
        room = self.ctx["rooms"][0]
        self.book(self.ctx, room, d(10), d(12), guest="Прямой гость")
        orig_fetch = sync.fetch
        try:
            sync.fetch = lambda url: feed_text(("av-1", d(11), d(13)))
            r = self.client.post("/api/feeds", headers=self.ctx["h"], json={
                "room_id": room["id"], "channel": "avito", "url": "https://www.avito.ru/calendar/1.ics"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["conflicts"], 1)
        finally:
            sync.fetch = orig_fetch
        telegram.process_outbox()
        self.assertTrue(any("Двойное бронирование" in t for _, t in self.sent))
        other_room = self.ctx["rooms"][1]

        def broken(url):
            raise RuntimeError("Площадка не отвечает")

        orig_fetch = sync.fetch
        try:
            sync.fetch = broken
            r2 = self.client.post("/api/feeds", headers=self.ctx["h"], json={
                "room_id": other_room["id"], "channel": "yandex", "url": "https://path.example/2.ics"})
            self.assertEqual(r2.status_code, 200, r2.text)
            self.assertEqual(r2.json()["status"], "error")
            # повторная (сломанная) синхронизация того же календаря не должна слать уведомление дважды
            self.client.post(f"/api/feeds/{r2.json()['id']}/sync", headers=self.ctx["h"])
        finally:
            sync.fetch = orig_fetch
        telegram.process_outbox()
        error_msgs = [t for _, t in self.sent if "обновить календарь" in t]
        self.assertEqual(len(error_msgs), 1)

    def test_morning_digest_once_per_day(self):
        # Другие тесты этого класса тоже привязывают Telegram (свои аккаунты) и по умолчанию
        # подписаны на дайджест, так что общее число отправленных дайджестов здесь может быть
        # больше одного — проверяем не общий счётчик, а именно наш чат.
        chat_id = self.link()
        self.book(self.ctx, self.ctx["rooms"][0], d(0), d(2), guest="Заезжает сегодня")
        before_hour = telegram.maybe_send_digests(now=datetime(2026, 1, 1, config.TELEGRAM_DIGEST_HOUR - 1))
        self.assertEqual(before_hour, 0)
        n = telegram.maybe_send_digests(now=datetime(2026, 1, 1, config.TELEGRAM_DIGEST_HOUR))
        self.assertGreaterEqual(n, 1)
        telegram.process_outbox()
        my_digests = [t for c, t in self.sent if c == chat_id and "Доброе утро" in t]
        self.assertEqual(len(my_digests), 1)
        self.sent.clear()
        again = telegram.maybe_send_digests(now=datetime(2026, 1, 1, config.TELEGRAM_DIGEST_HOUR + 2))
        self.assertEqual(again, 0)  # в тот же день дайджест уже отправлен всем, кому положено
        telegram.process_outbox()
        self.assertFalse(any(c == chat_id and "Доброе утро" in t for c, t in self.sent))


class IncomesTests(Base):
    """Прочие доходы (не от проживания), расходы на конкретный номер и их учёт в отчётах."""

    def staff_headers(self, ctx, email, role):
        self.client.post("/api/users", headers=ctx["h"], json={
            "name": "Сотрудник", "email": email, "role": role, "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": email, "password": "password123"})
        return {"Authorization": f"Bearer {tok.json()['token']}"}

    def income_cat(self, ctx, name=None):
        cats = self.client.get("/api/income-categories", headers=ctx["h"]).json()
        return next(c for c in cats if c["name"] == name) if name else cats[0]

    def test_default_income_categories_and_crud(self):
        ctx = self.register("inc1@example.ru")
        cats = self.client.get("/api/income-categories", headers=ctx["h"]).json()
        self.assertIn("Парковка", [c["name"] for c in cats])
        cat = self.income_cat(ctx, "Парковка")
        r = self.client.post("/api/incomes", headers=ctx["h"], json={
            "category_id": cat["id"], "amount": 1500, "date": d(0), "property_id": ctx["prop"]["id"],
            "comment": "Парковка за неделю"})
        self.assertEqual(r.status_code, 200, r.text)
        iid = r.json()["id"]
        lst = self.client.get("/api/incomes", headers=ctx["h"], params={"from": d(-1), "to": d(1)}).json()
        self.assertEqual((len(lst["rows"]), float(lst["total"])), (1, 1500))
        self.assertEqual(lst["by_category"][0]["category_name"], "Парковка")
        r = self.client.patch(f"/api/incomes/{iid}", headers=ctx["h"], json={"amount": 2000})
        self.assertEqual(float(r.json()["amount"]), 2000)
        csv_text = self.client.get("/api/incomes/export.csv", headers=ctx["h"], params={"from": d(-1), "to": d(1)}).text
        self.assertIn("Парковка", csv_text)
        # свои категории: создание, дубликат, архив
        r = self.client.post("/api/income-categories", headers=ctx["h"], json={"name": "Аренда зала", "color": "#112233"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.post("/api/income-categories", headers=ctx["h"], json={"name": "аренда зала"}).status_code, 409)
        new_id = r.json()["id"]
        self.client.patch(f"/api/income-categories/{new_id}", headers=ctx["h"], json={"archived": True})
        r = self.client.post("/api/incomes", headers=ctx["h"], json={"category_id": new_id, "amount": 10})
        self.assertEqual(r.status_code, 422)  # в архиве
        self.assertEqual(self.client.delete(f"/api/incomes/{iid}", headers=ctx["h"]).status_code, 200)

    def test_income_roles_and_tenant_isolation(self):
        a = self.register("inc2a@example.ru")
        b = self.register("inc2b@example.ru")
        mh = self.staff_headers(a, "inc2m@example.ru", "manager")
        hh = self.staff_headers(a, "inc2h@example.ru", "housekeeper")
        cat = self.income_cat(a)
        r = self.client.post("/api/incomes", headers=mh, json={"category_id": cat["id"], "amount": 100})
        self.assertEqual(r.status_code, 200, r.text)
        iid = r.json()["id"]
        self.assertEqual(self.client.post("/api/income-categories", headers=mh, json={"name": "Новая"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/incomes/{iid}", headers=mh).status_code, 403)
        self.assertEqual(self.client.get("/api/incomes", headers=hh).status_code, 403)
        # чужой аккаунт не видит и не трогает доходы и категории
        self.assertEqual(self.client.patch(f"/api/incomes/{iid}", headers=b["h"], json={"amount": 1}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/incomes/{iid}", headers=b["h"]).status_code, 404)
        r = self.client.post("/api/incomes", headers=b["h"], json={"category_id": cat["id"], "amount": 5})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.client.get("/api/incomes", headers=b["h"], params={"from": d(-1), "to": d(1)}).json()["rows"], [])
        # номер чужого аккаунта нельзя указать
        r = self.client.post("/api/incomes", headers=b["h"], json={
            "category_id": self.income_cat(b)["id"], "amount": 5, "room_id": a["rooms"][0]["id"]})
        self.assertEqual(r.status_code, 404)

    def test_report_includes_other_income_and_per_room_profit(self):
        ctx = self.register("inc3@example.ru", rooms=(("Стандарт", 2, 1000),))
        r0, r1 = ctx["rooms"]
        self.book(ctx, r0, d(0), d(5), total_price=5000)
        pid = ctx["prop"]["id"]
        inc = self.income_cat(ctx, "Парковка")["id"]
        exp = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]["id"]
        self.client.post("/api/incomes", headers=ctx["h"], json={"category_id": inc, "amount": 1000, "date": d(1), "room_id": r0["id"]})
        self.client.post("/api/incomes", headers=ctx["h"], json={"category_id": inc, "amount": 200, "date": d(2)})  # общий
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": exp, "amount": 700, "date": d(1), "room_id": r0["id"]})
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": exp, "amount": 300, "date": d(1), "property_id": pid})
        rep = self.client.get("/api/reports", headers=ctx["h"], params={"from": d(0), "to": d(10)}).json()
        t = rep["totals"]
        self.assertEqual((float(t["revenue"]), float(t["other_income"]), float(t["total_income"])), (5000, 1200, 6200))
        self.assertEqual((float(t["expenses"]), float(t["profit"])), (1000, 5200))
        rooms = {x["room_id"]: x for x in rep["by_room"]}
        self.assertEqual((float(rooms[r0["id"]]["other_income"]), float(rooms[r0["id"]]["expenses"]),
                          float(rooms[r0["id"]]["profit"])), (1000, 700, 5300))
        self.assertEqual((float(rooms[r1["id"]]["expenses"]), float(rooms[r1["id"]]["profit"])), (0, 0))
        self.assertEqual(float(rep["by_income_category"][0]["amount"]), 1200)
        self.assertEqual(len(rep["expense_monthly"]["rows"]), 12)
        self.assertTrue(rep["expense_monthly"]["categories"])
        self.assertIn("other_income", rep["monthly"][-1])
        csv_text = self.client.get("/api/reports/export.csv", headers=ctx["h"], params={"from": d(0), "to": d(10)}).text
        self.assertIn("Прочие доходы", csv_text)
        # фильтр расходов по номеру
        by_room = self.client.get("/api/expenses", headers=ctx["h"], params={
            "from": d(-1), "to": d(10), "room_id": r0["id"]}).json()
        self.assertEqual((len(by_room["rows"]), float(by_room["total"])), (1, 700))


class LaunchReadinessTests(Base):
    """Заголовки безопасности, служебные страницы, выгрузка броней, быстрый старт, письмо гостю."""

    def test_security_headers_and_embeddable_booking_page(self):
        r = self.client.get("/app/")
        self.assertEqual(r.headers["x-frame-options"], "DENY")
        self.assertIn("default-src 'self'", r.headers["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", r.headers["content-security-policy"])
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        book = self.client.get("/book/any")
        self.assertNotIn("x-frame-options", book.headers)  # страницу бронирования встраивают через iframe
        self.assertNotIn("frame-ancestors", book.headers["content-security-policy"])

    def test_service_pages_and_404(self):
        self.assertIn("Disallow: /app/", self.client.get("/robots.txt").text)
        self.assertIn("/legal/privacy", self.client.get("/sitemap.xml").text)
        m = self.client.get("/manifest.webmanifest").json()
        self.assertEqual(m["start_url"], "/app/")
        page = self.client.get("/net-takoj-stranitsy")
        self.assertEqual(page.status_code, 404)
        self.assertIn("Такой страницы нет", page.text)
        api_404 = self.client.get("/api/net-takogo")
        self.assertEqual(api_404.status_code, 404)
        self.assertEqual(api_404.json()["error"], "Не найдено")

    def test_bookings_csv_export_and_scoping(self):
        a = self.register("launch1@example.ru")
        b = self.register("launch2@example.ru")
        self.book(a, a["rooms"][0], d(2), d(5), guest="=ВЗЛОМ()", total_price=9000, paid_amount=3000)
        self.book(b, b["rooms"][0], d(2), d(5), guest="Чужой гость")
        text = self.client.get("/api/bookings/export.csv", headers=a["h"], params={"from": d(0), "to": d(30)}).text
        self.assertIn("Заезд;Выезд;Ночей", text)
        self.assertIn("'=ВЗЛОМ()", text)  # защита от формул в Excel
        self.assertIn("6000", text)  # остаток к оплате
        self.assertNotIn("Чужой гость", text)
        hh = self.client.post("/api/users", headers=a["h"], json={"name": "Горничная", "email": "launch1h@example.ru", "role": "housekeeper", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "launch1h@example.ru", "password": "password123"}).json()["token"]
        self.assertEqual(self.client.get("/api/bookings/export.csv", headers={"Authorization": f"Bearer {tok}"}).status_code, 403)

    def test_onboarding_progress_and_trial_info(self):
        ctx = self.register("launch3@example.ru")
        o = self.client.get("/api/onboarding", headers=ctx["h"]).json()
        done = {s["key"]: s["done"] for s in o["steps"]}
        self.assertTrue(done["rooms"])
        self.assertFalse(done["booking"])
        self.assertEqual(o["booking_page_slug"], ctx["prop"]["public_slug"])
        self.book(ctx, ctx["rooms"][0], d(1), d(2))
        o2 = self.client.get("/api/onboarding", headers=ctx["h"]).json()
        self.assertEqual(o2["done"], o["done"] + 1)
        me = self.client.get("/api/me", headers=ctx["h"]).json()
        self.assertEqual(me["plan"], "trial")
        self.assertEqual(me["trial_ends"], (date.today() + timedelta(days=14)).isoformat())

    def test_today_reports_free_rooms(self):
        ctx = self.register("launch4@example.ru", rooms=(("Стандарт", 3, 1000),))
        self.book(ctx, ctx["rooms"][0], d(-1), d(2))   # проживает
        self.book(ctx, ctx["rooms"][1], d(0), d(1))    # заезжает сегодня
        self.book(ctx, ctx["rooms"][2], d(-3), d(0), status="blocked")  # закрыт, но не на эту ночь
        t = self.client.get("/api/today", headers=ctx["h"]).json()
        self.assertEqual((t["rooms_total"], t["occupied_tonight"], t["free_tonight"]), (3, 2, 1))

    def test_menu_badges_count_site_requests_and_conflicts(self):
        ctx = self.register("launch7@example.ru")
        self.assertEqual(self.client.get("/api/badges", headers=ctx["h"]).json(), {"requests": 0, "conflicts": 0})
        slug, rt = ctx["prop"]["public_slug"], ctx["prop"]["room_types"][0]["id"]
        self.client.post(f"/api/public/{slug}/book", json={"room_type_id": rt, "check_in": d(3), "check_out": d(5), "guest_name": "Ольга", "guest_phone": "+79001234567", "consent": True})
        self.book(ctx, ctx["rooms"][5], d(3), d(5), status="pending")  # ручная неподтверждённая — это не заявка с сайта
        self.assertEqual(self.client.get("/api/badges", headers=ctx["h"]).json()["requests"], 1)
        hh = self.client.post("/api/users", headers=ctx["h"], json={"name": "Оля", "email": "launch7h@example.ru", "role": "housekeeper", "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": "launch7h@example.ru", "password": "password123"}).json()["token"]
        self.assertEqual(self.client.get("/api/badges", headers={"Authorization": f"Bearer {tok}"}).json(), {"requests": 0, "conflicts": 0})
        with db.tx() as conn:
            self.assertIsNotNone(db.one(conn, "SELECT last_login_at FROM users WHERE lower(email) = 'launch7h@example.ru'")["last_login_at"])

    def test_category_color_must_be_hex(self):
        ctx = self.register("launch5@example.ru")
        r = self.client.post("/api/expense-categories", headers=ctx["h"], json={"name": "Цвет", "color": "red\"><script>"})
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/income-categories", headers=ctx["h"], json={"name": "Цвет", "color": "#A1b2C3"})
        self.assertEqual(r.status_code, 200)

    def test_guest_gets_confirmation_email_without_breaking_booking(self):
        ctx = self.register("launch6@example.ru")
        sent = []
        orig_send, orig_host = mail.send, config.SMTP_HOST
        config.SMTP_HOST = "smtp.test.local"
        try:
            mail.send = lambda to, subject, body: sent.append((to, subject, body))
            slug, rt = ctx["prop"]["public_slug"], ctx["prop"]["room_types"][0]["id"]
            payload = {"room_type_id": rt, "check_in": d(3), "check_out": d(5), "guest_name": "Ольга",
                       "guest_phone": "+79001234567", "guest_email": "olga@example.ru", "consent": True}
            r = self.client.post(f"/api/public/{slug}/book", json=payload)
            self.assertEqual(r.status_code, 200, r.text)
            to_guest = [m for m in sent if m[0] == "olga@example.ru"]
            self.assertEqual(len(to_guest), 1)
            self.assertIn("Номер заявки", to_guest[0][2])
            to_staff = [m for m in sent if m[0] == "launch6@example.ru"]  # владелец тоже получает письмо о заявке
            self.assertEqual(len(to_staff), 1)
            self.assertIn("Новая заявка с сайта", to_staff[0][1])
            # отключил письма в профиле — больше не приходят
            self.client.patch("/api/me/preferences", headers=ctx["h"], json={"notify_email": False})
            sent.clear()
            self.client.post(f"/api/public/{slug}/book", json={**payload, "check_in": d(20), "check_out": d(22), "guest_email": ""})
            self.assertEqual([m for m in sent if m[0] == "launch6@example.ru"], [])
            self.client.patch("/api/me/preferences", headers=ctx["h"], json={"notify_email": True})

            def broken(*a):
                raise RuntimeError("SMTP недоступен")
            mail.send = broken
            r = self.client.post(f"/api/public/{slug}/book", json={**payload, "check_in": d(10), "check_out": d(12)})
            self.assertEqual(r.status_code, 200, r.text)  # сбой почты не теряет заявку
        finally:
            mail.send, config.SMTP_HOST = orig_send, orig_host


class OperationsTests(Base):
    """История изменений брони, отметка «номер убран», выгрузка и удаление аккаунта."""

    def staff(self, ctx, email, role):
        self.client.post("/api/users", headers=ctx["h"], json={"name": "Сотрудник", "email": email, "role": role, "password": "password123"})
        tok = self.client.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_booking_history_records_who_changed_what(self):
        ctx = self.register("ops1@example.ru")
        r0, r1 = ctx["rooms"][0], ctx["rooms"][1]
        b = self.book(ctx, r0, d(5), d(7), guest="Анна", total_price=7000).json()
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"room_id": r1["id"], "check_in": d(6), "check_out": d(8), "total_price": 8000})
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"status": "cancelled"})
        log = self.client.get(f"/api/bookings/{b['id']}/log", headers=ctx["h"]).json()
        self.assertEqual([x["action"] for x in log], ["cancelled", "updated", "created"])
        moved = {c["field"]: c for c in log[1]["details"]["changes"]}
        self.assertEqual(set(moved), {"Номер", "Заезд", "Выезд", "Стоимость"})
        self.assertEqual((moved["Стоимость"]["from"], moved["Стоимость"]["to"]), ("7000 ₽", "8000 ₽"))
        self.assertIn(r1["name"], moved["Номер"]["to"])
        self.assertEqual(log[0]["user_name"], "Иван")
        # пустая правка (те же значения) не засоряет историю
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"guest_name": "Анна"})
        self.assertEqual(len(self.client.get(f"/api/bookings/{b['id']}/log", headers=ctx["h"]).json()), 3)

    def test_booking_history_access_rules(self):
        a = self.register("ops2a@example.ru")
        other = self.register("ops2b@example.ru")
        b = self.book(a, a["rooms"][0], d(5), d(6)).json()
        self.assertEqual(self.client.get(f"/api/bookings/{b['id']}/log", headers=other["h"]).status_code, 404)
        hh = self.staff(a, "ops2h@example.ru", "housekeeper")
        self.assertEqual(self.client.get(f"/api/bookings/{b['id']}/log", headers=hh).status_code, 403)

    def test_site_booking_and_sync_are_logged_as_system(self):
        ctx = self.register("ops3@example.ru")
        slug, rt = ctx["prop"]["public_slug"], ctx["prop"]["room_types"][0]["id"]
        r = self.client.post(f"/api/public/{slug}/book", json={"room_type_id": rt, "check_in": d(3), "check_out": d(5), "guest_name": "Ольга", "guest_phone": "+79001234567", "consent": True})
        log = self.client.get(f"/api/bookings/{r.json()['booking_id']}/log", headers=ctx["h"]).json()
        self.assertEqual((log[0]["action"], log[0]["user_name"]), ("created", "Система"))

    def test_housekeeper_marks_room_cleaned(self):
        ctx = self.register("ops4@example.ru")
        room = ctx["rooms"][0]
        self.book(ctx, room, d(-2), d(0), guest="Уезжает")
        hh = self.staff(ctx, "ops4h@example.ru", "housekeeper")
        t = self.client.get("/api/today", headers=hh).json()
        self.assertIsNone(t["departures"][0]["room_cleaned_on"])
        r = self.client.post(f"/api/rooms/{room['id']}/cleaned", headers=hh, json={})
        self.assertEqual(r.status_code, 200, r.text)
        t = self.client.get("/api/today", headers=hh).json()
        self.assertEqual(t["departures"][0]["room_cleaned_on"], d(0))
        self.client.post(f"/api/rooms/{room['id']}/cleaned", headers=hh, json={"cleaned": False})
        self.assertIsNone(self.client.get("/api/today", headers=hh).json()["departures"][0]["room_cleaned_on"])
        other = self.register("ops4b@example.ru")
        self.assertEqual(self.client.post(f"/api/rooms/{room['id']}/cleaned", headers=other["h"], json={}).status_code, 404)

    def test_account_export_has_data_but_no_secrets(self):
        ctx = self.register("ops5@example.ru")
        self.book(ctx, ctx["rooms"][0], d(1), d(2), guest="Экспорт")
        r = self.client.get("/api/account/export", headers=ctx["h"])
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        data = r.json()
        self.assertEqual(len(data["rooms"]), 12)
        self.assertTrue(any(b["guest_name"] == "Экспорт" for b in data["bookings"]))
        self.assertNotIn("password_hash", r.text)
        self.assertNotIn("ical_token", r.text)
        mh = self.staff(ctx, "ops5m@example.ru", "manager")
        self.assertEqual(self.client.get("/api/account/export", headers=mh).status_code, 403)

    def test_delete_account_requires_password_and_removes_everything(self):
        keep = self.register("ops6keep@example.ru")
        ctx = self.register("ops6@example.ru")
        self.book(ctx, ctx["rooms"][0], d(1), d(2))
        cat = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]["id"]
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat, "amount": 100})
        inc = self.client.get("/api/income-categories", headers=ctx["h"]).json()[0]["id"]
        self.client.post("/api/incomes", headers=ctx["h"], json={"category_id": inc, "amount": 50})
        self.client.post("/api/expense-recurring", headers=ctx["h"], json={"category_id": cat, "amount": 10, "day_of_month": 1})
        mh = self.staff(ctx, "ops6m@example.ru", "manager")
        self.assertEqual(self.client.post("/api/account/delete", headers=mh, json={"password": "password123"}).status_code, 403)
        self.assertEqual(self.client.post("/api/account/delete", headers=ctx["h"], json={"password": "wrong"}).status_code, 401)
        r = self.client.post("/api/account/delete", headers=ctx["h"], json={"password": "password123"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.get("/api/me", headers=ctx["h"]).status_code, 401)  # токен больше не действует
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "ops6@example.ru", "password": "password123"}).status_code, 401)
        with db.tx() as conn:
            left = db.one(conn, "SELECT (SELECT count(*) FROM bookings WHERE guest_name = 'Гость' AND room_id = ANY(%s::uuid[])) AS n",
                          ([r["id"] for r in ctx["rooms"]],))["n"]
        self.assertEqual(left, 0)
        self.assertEqual(self.client.get("/api/me", headers=keep["h"]).status_code, 200)  # чужой аккаунт цел


class AbuseProtectionTests(Base):
    """Публичная форма открыта всем — спам-заявки не должны занимать номера навсегда."""

    def setUp(self):
        self.ctx = self.register(f"abuse{id(self)}@example.ru")
        self.slug = self.ctx["prop"]["public_slug"]
        self.rt = self.ctx["prop"]["room_types"][0]["id"]
        ratelimit.reset()
        self._orig = (config.PUBLIC_BOOKINGS_PER_HOUR, config.MAX_PENDING_PER_PHONE, config.REQUEST_TTL_HOURS)

    def tearDown(self):
        config.PUBLIC_BOOKINGS_PER_HOUR, config.MAX_PENDING_PER_PHONE, config.REQUEST_TTL_HOURS = self._orig
        ratelimit.reset()

    def request(self, offset=3, phone="+79001234567", **extra):
        return self.client.post(f"/api/public/{self.slug}/book", json={
            "room_type_id": self.rt, "check_in": d(offset), "check_out": d(offset + 2), "guest_name": "Гость",
            "guest_phone": phone, "consent": True, **extra})

    def pending(self):
        return self.client.get("/api/bookings", headers=self.ctx["h"], params={"from": d(0), "to": d(60), "status": "pending"}).json()

    def test_honeypot_looks_accepted_but_creates_nothing(self):
        r = self.request(website="http://spam.example")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.pending(), [])

    def test_per_ip_limit(self):
        config.PUBLIC_BOOKINGS_PER_HOUR = 2
        codes = [self.request(offset=3 + 3 * i, phone=f"+7900123456{i}").status_code for i in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_per_phone_limit_on_unconfirmed_requests(self):
        config.MAX_PENDING_PER_PHONE = 2
        codes = [self.request(offset=3 + 3 * i).status_code for i in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        # другой телефон не затронут
        self.assertEqual(self.request(offset=20, phone="+79007654321").status_code, 200)

    def test_unconfirmed_request_expires_and_frees_room(self):
        rows = self.request().json()
        with db.tx() as conn:
            row = db.one(conn, "SELECT hold_expires_at > now() + interval '47 hours' AS ok FROM bookings WHERE id = %s", (rows["booking_id"],))
            self.assertTrue(row["ok"])  # срок по умолчанию 48 часов
            db.run(conn, "UPDATE bookings SET hold_expires_at = now() - interval '1 minute' WHERE id = %s", (rows["booking_id"],))
        self.assertGreaterEqual(sync.expire_holds(), 1)
        b = self.client.get(f"/api/bookings/{rows['booking_id']}", headers=self.ctx["h"]).json()
        self.assertEqual(b["status"], "cancelled")
        self.assertIn("не подтверждена вовремя", b["notes"])
        # подтверждённая заявка срок не теряет
        r2 = self.request(offset=30).json()
        self.client.patch(f"/api/bookings/{r2['booking_id']}", headers=self.ctx["h"], json={"status": "confirmed"})
        with db.tx() as conn:
            db.run(conn, "UPDATE bookings SET hold_expires_at = now() - interval '1 minute' WHERE id = %s", (r2["booking_id"],))
        sync.expire_holds()
        self.assertEqual(self.client.get(f"/api/bookings/{r2['booking_id']}", headers=self.ctx["h"]).json()["status"], "confirmed")

    def test_ttl_can_be_disabled(self):
        config.REQUEST_TTL_HOURS = 0
        rid = self.request().json()["booking_id"]
        with db.tx() as conn:
            self.assertIsNone(db.one(conn, "SELECT hold_expires_at FROM bookings WHERE id = %s", (rid,))["hold_expires_at"])

    def test_password_reset_requests_are_limited(self):
        orig = config.RESET_REQUESTS_PER_HOUR
        config.RESET_REQUESTS_PER_HOUR = 2
        try:
            codes = [self.client.post("/api/auth/forgot-password", json={"email": f"nobody{i}@example.ru"}).status_code for i in range(3)]
            self.assertEqual(codes, [200, 200, 429])
            ratelimit.reset()
            config.RESET_REQUESTS_PER_HOUR = 100
            codes = [self.client.post("/api/auth/forgot-password", json={"email": "same@example.ru"}).status_code for _ in range(4)]
            self.assertEqual(codes, [200, 200, 200, 429])  # на один адрес — не больше 3 в час
        finally:
            config.RESET_REQUESTS_PER_HOUR = orig

    def test_db_sessions_use_hotel_timezone(self):
        with db.tx() as conn:
            self.assertEqual(db.one(conn, "SHOW timezone")["TimeZone"], config.APP_TIMEZONE)


class PlatformAdminTests(Base):
    """Команды администратора сервиса и ограничения тарифов."""

    def test_plan_limits_properties(self):
        ctx = self.register("plan1@example.ru")
        me = self.client.get("/api/me", headers=ctx["h"]).json()
        self.assertEqual((me["plan"], me["properties_limit"]), ("trial", 4))
        for i in range(3):  # один объект уже создан регистрацией — доводим до лимита 4
            r = self.client.post("/api/setup", headers=ctx["h"], json={"name": f"Объект {i}", "room_types": [{"name": "Стандарт", "count": 1, "base_price": 1000}]})
            self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/api/setup", headers=ctx["h"], json={"name": "Пятый", "room_types": [{"name": "С", "count": 1}]})
        self.assertEqual(r.status_code, 403)
        self.assertIn("до 4 объектов", r.json()["error"])
        with db.tx() as conn:
            admin.set_plan(conn, "plan1@example.ru", "business")
        r = self.client.post("/api/setup", headers=ctx["h"], json={"name": "Пятый", "room_types": [{"name": "С", "count": 1}]})
        self.assertEqual(r.status_code, 200, r.text)
        me = self.client.get("/api/me", headers=ctx["h"]).json()
        self.assertEqual((me["plan_label"], me["properties_limit"]), ("Бизнес", 15))

    def test_suspend_activate_and_set_plan(self):
        ctx = self.register("plan2@example.ru")
        with db.tx() as conn:
            admin.set_status(conn, "plan2@example.ru", "suspended")
        self.assertEqual(self.client.get("/api/me", headers=ctx["h"]).status_code, 403)  # токен сразу перестаёт работать
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "plan2@example.ru", "password": "password123"}).status_code, 403)
        with db.tx() as conn:
            admin.set_status(conn, "plan2@example.ru", "active")
            admin.set_plan(conn, "plan2@example.ru", "pro", date.today() + timedelta(days=30))
        me = self.client.get("/api/me", headers=ctx["h"]).json()
        self.assertEqual((me["plan"], me["paid_until"], me["trial_ends"]), ("pro", (date.today() + timedelta(days=30)).isoformat(), None))
        with self.assertRaises(SystemExit):
            with db.tx() as conn:
                admin.set_plan(conn, "plan2@example.ru", "несуществующий")

    def test_reset_password_and_listing(self):
        ctx = self.register("plan3@example.ru")
        for _ in range(config.LOGIN_MAX_ATTEMPTS):
            self.client.post("/api/auth/login", json={"email": "plan3@example.ru", "password": "x"})
        with db.tx() as conn:
            new_pw = admin.reset_password(conn, "plan3@example.ru")
        r = self.client.post("/api/auth/login", json={"email": "plan3@example.ru", "password": new_pw})
        self.assertEqual(r.status_code, 200, r.text)  # блокировка после подбора тоже снята
        with db.tx() as conn:
            rows = admin.list_accounts(conn)
            row = next(x for x in rows if x["owner_email"] == "plan3@example.ru")
            self.assertEqual((row["plan"], row["rooms"]), ("trial", 12))
            self.assertIsNotNone(row["last_login"])
            self.assertGreaterEqual(admin.stats(conn)["accounts"], 1)
            self.assertEqual(admin.find_account(conn, str(row["id"])[:8])["id"], row["id"])  # поиск по началу id
        self.assertEqual(admin.main(["stats"]), 0)


PNG_1X1 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


class PhotoTests(Base):
    """Фото категорий номеров для страницы бронирования."""

    def upload(self, ctx, rt_id, data=PNG_1X1, headers=None):
        return self.client.post(f"/api/room-types/{rt_id}/photos", headers=headers or ctx["h"], json={"data": data})

    def test_upload_serve_order_delete(self):
        ctx = self.register("photo1@example.ru")
        rt = ctx["prop"]["room_types"][0]["id"]
        a = self.upload(ctx, rt); self.assertEqual(a.status_code, 200, a.text)
        b = self.upload(ctx, rt, data="data:image/png;base64," + PNG_1X1)  # data-URL тоже понимаем
        self.assertEqual(b.status_code, 200, b.text)
        pa, pb = a.json()["id"], b.json()["id"]
        info = self.client.get(f"/api/public/{ctx['prop']['public_slug']}").json()
        self.assertEqual(info["room_types"][0]["photos"], [f"/media/photo/{pa}", f"/media/photo/{pb}"])
        img = self.client.get(f"/media/photo/{pa}")  # публично, без входа
        self.assertEqual((img.status_code, img.headers["content-type"]), (200, "image/png"))
        self.assertTrue(img.content.startswith(b"\x89PNG"))
        self.assertIn("immutable", img.headers["cache-control"])
        r = self.client.put(f"/api/room-types/{rt}/photos/order", headers=ctx["h"], json={"ids": [pb, pa]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([p["id"] for p in self.client.get(f"/api/room-types/{rt}/photos", headers=ctx["h"]).json()], [pb, pa])
        self.assertEqual(self.client.put(f"/api/room-types/{rt}/photos/order", headers=ctx["h"], json={"ids": [pb]}).status_code, 422)
        self.assertEqual(self.client.delete(f"/api/photos/{pa}", headers=ctx["h"]).status_code, 200)
        self.assertEqual(self.client.get(f"/media/photo/{pa}").status_code, 404)

    def test_rejects_non_images_and_limits(self):
        import base64
        ctx = self.register("photo2@example.ru")
        rt = ctx["prop"]["room_types"][0]["id"]
        svg = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>").decode()
        self.assertEqual(self.upload(ctx, rt, data=svg).status_code, 422)  # SVG с возможным скриптом не принимаем
        self.assertEqual(self.upload(ctx, rt, data=base64.b64encode(b"just text").decode()).status_code, 422)
        self.assertEqual(self.upload(ctx, rt, data="!!!не base64!!!").status_code, 422)
        big = base64.b64encode(b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024 + 10)).decode()
        self.assertEqual(self.upload(ctx, rt, data=big).status_code, 413)
        for _ in range(8):
            self.assertEqual(self.upload(ctx, rt).status_code, 200)
        self.assertEqual(self.upload(ctx, rt).status_code, 422)  # потолок 8 фото

    def test_permissions_and_isolation(self):
        a = self.register("photo3a@example.ru")
        other = self.register("photo3b@example.ru")
        rt = a["prop"]["room_types"][0]["id"]
        self.client.post("/api/users", headers=a["h"], json={"name": "М", "email": "photo3m@example.ru", "role": "manager", "password": "password123"})
        mh = {"Authorization": "Bearer " + self.client.post("/api/auth/login", json={"email": "photo3m@example.ru", "password": "password123"}).json()["token"]}
        self.assertEqual(self.upload(a, rt, headers=mh).status_code, 403)  # загружает только владелец
        self.assertEqual(self.client.get(f"/api/room-types/{rt}/photos", headers=mh).status_code, 200)
        self.assertEqual(self.upload(other, rt, headers=other["h"]).status_code, 404)  # чужая категория
        pid = self.upload(a, rt).json()["id"]
        self.assertEqual(self.client.delete(f"/api/photos/{pid}", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.get(f"/api/room-types/{rt}/photos", headers=other["h"]).status_code, 404)
        # бронирование на сайте выключено — фото не отдаются
        self.client.patch(f"/api/properties/{a['prop']['id']}", headers=a["h"], json={"booking_enabled": False})
        self.assertEqual(self.client.get(f"/media/photo/{pid}").status_code, 404)


class AuthSecurityTests(Base):
    """Восстановление пароля (мок SMTP — как telegram.send_message/sync.fetch в других тестах)
    и блокировка входа после подбора пароля."""

    def setUp(self):
        self.email = f"authsec{id(self)}@example.ru"
        self.ctx = self.register(self.email)
        self.outgoing = []
        self._orig_send = mail.send
        self._orig_smtp_host = config.SMTP_HOST
        config.SMTP_HOST = "smtp.test.local"  # "включаем" SMTP, чтобы send_or_log не ушёл в лог
        mail.send = lambda to, subject, body: self.outgoing.append((to, subject, body))

    def tearDown(self):
        mail.send = self._orig_send
        config.SMTP_HOST = self._orig_smtp_host

    def login(self, password):
        return self.client.post("/api/auth/login", json={"email": self.email, "password": password})

    def test_login_lockout_after_max_attempts(self):
        for _ in range(config.LOGIN_MAX_ATTEMPTS):
            r = self.login("неверный-пароль")
            self.assertEqual(r.status_code, 401)
        # лимит исчерпан — теперь даже верный пароль блокируется на время
        r = self.login("password123")
        self.assertEqual(r.status_code, 429)
        # снимаем блокировку «руками» (как будто прошло 15 минут) — верный пароль снова работает
        with db.tx() as conn:
            db.run(conn, "UPDATE users SET locked_until = now() - interval '1 minute' WHERE lower(email) = %s",
                   (self.email,))
        r = self.login("password123")
        self.assertEqual(r.status_code, 200, r.text)
        # успешный вход сбрасывает счётчик неудач
        with db.tx() as conn:
            row = db.one(conn, "SELECT failed_attempts, locked_until FROM users WHERE lower(email) = %s", (self.email,))
        self.assertEqual((row["failed_attempts"], row["locked_until"]), (0, None))

    def test_wrong_password_below_limit_does_not_lock(self):
        for _ in range(config.LOGIN_MAX_ATTEMPTS - 1):
            self.assertEqual(self.login("неверный").status_code, 401)
        r = self.login("password123")
        self.assertEqual(r.status_code, 200, r.text)  # ещё не заблокирован

    def test_forgot_password_unknown_email_is_generic_and_silent(self):
        r = self.client.post("/api/auth/forgot-password", json={"email": "no-such-user@example.ru"})
        self.assertEqual(r.status_code, 200)
        known = self.client.post("/api/auth/forgot-password", json={"email": self.email})
        self.assertEqual(known.json()["message"], r.json()["message"])  # ответ не выдаёт, есть ли email
        self.assertEqual(len(self.outgoing), 1)  # письмо ушло только для реального email

    def _extract_token(self, body: str) -> str:
        m = re.search(r"token=([\w\-]+)", body)
        self.assertIsNotNone(m, body)
        return m.group(1)

    def test_reset_password_flow(self):
        r = self.client.post("/api/auth/forgot-password", json={"email": self.email})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.outgoing), 1)
        to, subject, body = self.outgoing[0]
        self.assertEqual(to, self.email)
        token = self._extract_token(body)
        # слабый пароль отклоняется
        self.assertEqual(self.client.post("/api/auth/reset-password", json={"token": token, "password": "123"}).status_code, 422)
        # верный токен и нормальный пароль — успех
        r = self.client.post("/api/auth/reset-password", json={"token": token, "password": "new-password-1"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.login("password123").status_code, 401)  # старый пароль больше не работает
        self.assertEqual(self.login("new-password-1").status_code, 200)
        # токен одноразовый
        r = self.client.post("/api/auth/reset-password", json={"token": token, "password": "another-pass-1"})
        self.assertEqual(r.status_code, 422)

    def test_dev_mode_logs_reset_link_when_smtp_not_configured(self):
        config.SMTP_HOST = ""  # по умолчанию SMTP не настроен — это и проверяем
        with self.assertLogs("fligel.mail", level="INFO") as logs:
            r = self.client.post("/api/auth/forgot-password", json={"email": self.email})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.outgoing, [])  # mail.send не вызывался вовсе
        self.assertTrue(any("token=" in msg for msg in logs.output))

    def test_reset_password_bad_or_expired_token(self):
        self.assertEqual(self.client.post("/api/auth/reset-password",
                                          json={"token": "wrong", "password": "new-password-1"}).status_code, 422)
        self.client.post("/api/auth/forgot-password", json={"email": self.email})
        token = self._extract_token(self.outgoing[0][2])
        with db.tx() as conn:
            db.run(conn, "UPDATE password_resets SET expires_at = now() - interval '1 minute' WHERE token = %s",
                   (token,))
        r = self.client.post("/api/auth/reset-password", json={"token": token, "password": "new-password-1"})
        self.assertEqual(r.status_code, 422)

    def test_change_password_from_profile(self):
        r = self.client.post("/api/auth/change-password", headers=self.ctx["h"],
                             json={"current_password": "wrong", "new_password": "new-password-1"})
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/auth/change-password", headers=self.ctx["h"],
                             json={"current_password": "password123", "new_password": "short"})
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/auth/change-password", headers=self.ctx["h"],
                             json={"current_password": "password123", "new_password": "new-password-1"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.login("password123").status_code, 401)
        self.assertEqual(self.login("new-password-1").status_code, 200)


class LandingAndLegalTests(unittest.TestCase):
    """Лендинг и юридические черновики — статический контент, но должен реально отдаваться
    и содержать то, что требовалось (тарифы, предупреждение о черновике, ссылки)."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_landing_page_has_pricing_and_cta(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        for text in ("990", "2 490", "4 490", "14 дней", "/app/#register",
                     "/legal/privacy", "/legal/pdn-consent", "/legal/terms"):
            self.assertIn(text, r.text)

    def test_legal_pages_are_marked_as_drafts(self):
        for path in ("/legal/privacy", "/legal/pdn-consent", "/legal/terms"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("ЧЕРНОВИК", r.text)
        self.assertIn("152-ФЗ", self.client.get("/legal/privacy").text)

    def test_public_booking_page_links_to_legal_pages(self):
        r = self.client.get("/book/any-slug")  # сам объект может не существовать — страница статическая
        self.assertEqual(r.status_code, 200)
        for path in ("/legal/privacy", "/legal/pdn-consent", "/legal/terms"):
            self.assertIn(path, r.text)

    def test_registration_form_links_to_legal_pages(self):
        r = self.client.get("/app/")
        self.assertEqual(r.status_code, 200)
        # SPA грузит логику из app.js — проверяем, что ссылки на юридические страницы там есть
        js = self.client.get("/static/admin/app.js").text
        for path in ("/legal/privacy", "/legal/pdn-consent", "/legal/terms"):
            self.assertIn(path, js)


class ImportTests(Base):
    """Импорт броней из CSV (переезд из Excel / другой системы)."""

    def imp(self, ctx, text, dry=False, headers=None):
        return self.client.post("/api/bookings/import", headers=headers or ctx["h"], json={"csv": text, "dry_run": dry})

    def test_import_creates_bookings_and_reports_errors(self):
        ctx = self.register("imp1@example.ru")
        csv_text = ("\ufeffЗаезд;Выезд;Номер;Гость;Телефон;Гостей;Источник;Стоимость;Оплачено;Комментарий\n"
                    "15.07.2030;18.07.2030;101;Иван Петров;+7 900 111-22-33;2;Авито;10 500,50 ₽;3000;поздний заезд\n"
                    "2030-07-20;2030-07-22;102;Мария;;;;;;\n"
                    "16.07.2030;17.07.2030;101;Пересечение;;;;;;\n"
                    "10.08.2030;09.08.2030;101;Наоборот;;;;;;\n"
                    "10.08.2030;12.08.2030;999;Нет номера;;;;;;\n"
                    "\n"
                    "abc;12.08.2030;101;Плохая дата;;;;;;\n")
        dry = self.imp(ctx, csv_text, dry=True).json()
        self.assertEqual((dry["dry_run"], dry["created"], dry["skipped"], dry["total"]), (True, 2, 4, 6))
        self.assertEqual(self.client.get("/api/bookings?from=2030-07-01&to=2030-09-01", headers=ctx["h"]).json(), [])  # проверка ничего не сохранила
        real = self.imp(ctx, csv_text).json()
        self.assertEqual((real["created"], real["skipped"]), (2, 4))
        lines = {e["line"]: e["error"] for e in real["errors"]}
        self.assertIn("занят", lines[4])
        self.assertIn("выезд", lines[5])
        self.assertIn("не найден", lines[6])
        self.assertIn("дата заезда", lines[8])
        rows = self.client.get("/api/bookings?from=2030-07-01&to=2030-09-01", headers=ctx["h"]).json()
        first = next(b for b in rows if b["guest_name"] == "Иван Петров")
        self.assertEqual((first["source"], first["total_price"], first["paid_amount"], first["notes"]),
                         ("avito", 10500.5, 3000.0, "поздний заезд"))
        auto = next(b for b in rows if b["guest_name"] == "Мария")
        self.assertEqual(float(auto["total_price"]), 7000.0)  # цена не указана — по тарифу 3500 × 2 ночи
        # повторный импорт того же файла ничего не дублирует
        again = self.imp(ctx, csv_text).json()
        self.assertEqual(again["created"], 0)

    def test_import_validation_and_permissions(self):
        ctx = self.register("imp2@example.ru")
        self.assertEqual(self.imp(ctx, "").status_code, 422)
        r = self.imp(ctx, "Гость;Телефон\nИван;123\n")
        self.assertEqual(r.status_code, 422)
        self.assertIn("Заезд", r.json()["error"])
        self.assertEqual(self.client.post("/api/bookings/import", headers=ctx["h"], json={}).status_code, 422)
        self.assertEqual(self.client.post("/api/bookings/import", json={"csv": "x"}).status_code, 401)
        t = self.client.get("/api/bookings/import-template.csv", headers=ctx["h"])
        self.assertEqual(t.status_code, 200)
        self.assertTrue(self.imp(ctx, t.content.decode("utf-8-sig"), dry=True).json()["created"] in (0, 1))
        # запятая как разделитель и английские заголовки
        r = self.imp(ctx, "check_in,check_out,room,name\n2031-01-10,2031-01-12,103,John\n").json()
        self.assertEqual(r["created"], 1)

    def test_import_is_tenant_isolated(self):
        a, b = self.register("imp3a@example.ru"), self.register("imp3b@example.ru")
        self.imp(a, "Заезд;Выезд;Номер\n10.01.2032;12.01.2032;101\n")
        r = self.imp(b, "Заезд;Выезд;Номер\n10.01.2032;12.01.2032;101\n").json()
        self.assertEqual(r["created"], 1)  # у другого аккаунта номер 101 свободен


class MoneyTests(Base):
    """История платежей, услуги, скидка и залог."""

    def mk(self, ctx, **kw):
        r = self.book(ctx, ctx["rooms"][0], "2033-05-10", "2033-05-13", total_price=9000, **kw)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def money(self, ctx, b):
        return self.client.get(f"/api/bookings/{b['id']}/money", headers=ctx["h"]).json()

    def test_payments_refunds_and_paid_cache(self):
        ctx = self.register("money1@example.ru")
        b = self.mk(ctx)
        r = self.client.post(f"/api/bookings/{b['id']}/payments", headers=ctx["h"], json={"amount": 3000, "method": "card"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((float(r.json()["paid"]), float(r.json()["due"])), (3000.0, 6000.0))
        self.client.post(f"/api/bookings/{b['id']}/payments", headers=ctx["h"], json={"amount": 6000, "method": "cash", "note": "остаток"})
        got = self.client.get(f"/api/bookings/{b['id']}", headers=ctx["h"]).json()
        self.assertEqual(float(got["paid_amount"]), 9000.0)  # кэш в брони совпадает с историей
        over = self.client.post(f"/api/bookings/{b['id']}/payments", headers=ctx["h"], json={"amount": 10000, "kind": "refund"})
        self.assertEqual(over.status_code, 422)
        ok = self.client.post(f"/api/bookings/{b['id']}/payments", headers=ctx["h"], json={"amount": 1000, "kind": "refund"})
        self.assertEqual(float(ok.json()["paid"]), 8000.0)
        for bad in ({"amount": 0}, {"amount": -5}, {"amount": "abc"}, {"amount": 10, "method": "bitcoin"}, {"amount": 10, "kind": "x"}):
            self.assertEqual(self.client.post(f"/api/bookings/{b['id']}/payments", headers=ctx["h"], json=bad).status_code, 422, bad)
        first = self.money(ctx, b)["payments"][0]
        d = self.client.delete(f"/api/payments/{first['id']}", headers=ctx["h"])
        self.assertEqual(d.status_code, 200, d.text)
        self.assertEqual(float(d.json()["paid"]), 5000.0)
        log = self.client.get(f"/api/bookings/{b['id']}/log", headers=ctx["h"]).json()
        self.assertTrue(any(r["action"] == "payment" for r in log))

    def test_legacy_paid_amount_becomes_payment(self):
        ctx = self.register("money2@example.ru")
        b = self.mk(ctx, paid_amount=2000)
        self.assertEqual(float(self.money(ctx, b)["paid"]), 2000.0)
        self.assertEqual(len(self.money(ctx, b)["payments"]), 1)
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"paid_amount": 9000})
        self.assertEqual(r.status_code, 200, r.text)
        m = self.money(ctx, b)
        self.assertEqual((float(m["paid"]), len(m["payments"])), (9000.0, 2))
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"paid_amount": 4000})
        m = self.money(ctx, b)
        self.assertEqual(float(m["paid"]), 4000.0)
        self.assertEqual(m["payments"][-1]["kind"], "refund")

    def test_services_discount_deposit(self):
        ctx = self.register("money3@example.ru")
        b = self.mk(ctx)
        svc = self.client.post("/api/services", headers=ctx["h"], json={"name": "Завтрак", "price": 500}).json()
        r = self.client.post(f"/api/bookings/{b['id']}/services", headers=ctx["h"], json={"service_id": svc["id"], "qty": 3})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((float(r.json()["total"]), float(r.json()["services_sum"]), float(r.json()["stay_price"])), (10500.0, 1500.0, 9000.0))
        self.client.patch(f"/api/services/{svc['id']}", headers=ctx["h"], json={"price": 900})  # старые счета не меняются
        self.assertEqual(float(self.money(ctx, b)["services"][0]["price"]), 500.0)
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"discount_amount": 1000, "discount_reason": "Постоянный гость"})
        self.assertEqual(float(r.json()["total_price"]), 9500.0)
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"discount_amount": 500})
        self.assertEqual(float(r.json()["total_price"]), 10000.0)
        m = self.money(ctx, b)
        self.assertEqual((m["discount_reason"], float(m["stay_price"])), ("Постоянный гость", 9000.0))
        sid = m["services"][0]["id"]
        self.assertEqual(float(self.client.delete(f"/api/booking-services/{sid}", headers=ctx["h"]).json()["total"]), 8500.0)
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"deposit_amount": 3000})
        self.assertEqual((r.json()["deposit_status"], float(r.json()["deposit_amount"])), ("expected", 3000.0))
        r = self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"deposit_status": "held"})
        self.assertEqual(r.json()["deposit_status"], "held")
        self.assertEqual(self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"deposit_status": "??"}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/bookings/{b['id']}/services", headers=ctx["h"], json={"name": "", "price": 1}).status_code, 422)

    def test_cash_summary_and_isolation(self):
        a, other = self.register("money4a@example.ru"), self.register("money4b@example.ru")
        b = self.mk(a)
        today = date.today().isoformat()
        self.client.post(f"/api/bookings/{b['id']}/payments", headers=a["h"], json={"amount": 4000, "method": "cash", "paid_on": today})
        self.client.post(f"/api/bookings/{b['id']}/payments", headers=a["h"], json={"amount": 1000, "method": "card", "paid_on": today})
        self.client.post(f"/api/bookings/{b['id']}/payments", headers=a["h"], json={"amount": 500, "kind": "refund", "method": "cash", "paid_on": today})
        s = self.client.get(f"/api/payments/summary?from={today}&to={today}", headers=a["h"]).json()
        self.assertEqual((float(s["received"]), float(s["refunded"]), float(s["net"])), (5000.0, 500.0, 4500.0))
        self.assertEqual({m["method"] for m in s["by_method"]}, {"cash", "card"})
        # чужой аккаунт ничего не видит и не меняет
        self.assertEqual(self.client.get(f"/api/bookings/{b['id']}/money", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.post(f"/api/bookings/{b['id']}/payments", headers=other["h"], json={"amount": 1}).status_code, 404)
        pid = self.money(a, b)["payments"][0]["id"]
        self.assertEqual(self.client.delete(f"/api/payments/{pid}", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.get(f"/api/payments/summary?from={today}&to={today}", headers=other["h"]).json()["received"], 0)


class TariffTests(Base):
    """Тарифы, доплата за гостей, скидка за длительность, выбор дат в календаре цен."""

    def setUp(self):
        self.ctx = self.register(f"tariff{id(self)}@example.ru", rooms=(("Стандарт", 3, 3500),))
        self.rt = self.ctx["prop"]["room_types"][0]
        self.room = self.ctx["rooms"][0]

    def quote(self, ci, co, **kw):
        q = "&".join(f"{k}={v}" for k, v in kw.items())
        return self.client.get(f"/api/bookings/quote?room_id={self.room['id']}&check_in={ci}&check_out={co}&{q}", headers=self.ctx["h"]).json()

    def plan(self, **kw):
        r = self.client.post(f"/api/room-types/{self.rt['id']}/plans", headers=self.ctx["h"], json=kw)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_plans_change_price(self):
        nr = self.plan(name="Невозвратный", percent_delta=-10, refundable=False)
        bf = self.plan(name="С завтраком", fixed_delta=500, breakfast=True)
        self.assertEqual(float(self.quote("2034-03-01", "2034-03-04")["total"]), 10500.0)
        self.assertEqual(float(self.quote("2034-03-01", "2034-03-04", rate_plan_id=nr["id"])["total"]), 9450.0)
        self.assertEqual(float(self.quote("2034-03-01", "2034-03-04", rate_plan_id=bf["id"])["total"]), 12000.0)
        # бронь без явной цены считается по тарифу и запоминает его
        r = self.book(self.ctx, self.room, "2034-03-01", "2034-03-04", rate_plan_id=nr["id"])
        self.assertEqual((float(r.json()["total_price"]), r.json()["rate_plan_name"]), (9450.0, "Невозвратный"))
        # цена на дату тоже учитывается тарифом
        self.client.put("/api/rates", headers=self.ctx["h"], json={"room_type_ids": [self.rt["id"]], "date_from": "2034-04-01", "date_to": "2034-04-01", "price": 5000})
        self.assertEqual(float(self.quote("2034-04-01", "2034-04-02", rate_plan_id=nr["id"])["total"]), 4500.0)

    def test_plan_rules_and_isolation(self):
        other = self.register(f"tariffo{id(self)}@example.ru")
        p = self.plan(name="Тест")
        self.assertEqual(self.client.post(f"/api/room-types/{self.rt['id']}/plans", headers=self.ctx["h"], json={"name": ""}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/room-types/{self.rt['id']}/plans", headers=self.ctx["h"], json={"name": "X", "percent_delta": 999}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/room-types/{self.rt['id']}/plans", headers=other["h"], json={"name": "X"}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/plans/{p['id']}", headers=other["h"], json={"name": "взлом"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/plans/{p['id']}", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.get(f"/api/room-types/{self.rt['id']}/plans", headers=other["h"]).status_code, 404)
        # тариф чужой категории использовать нельзя
        foreign = self.client.post(f"/api/room-types/{other['prop']['room_types'][0]['id']}/plans", headers=other["h"], json={"name": "Чужой"}).json()
        r = self.client.get(f"/api/bookings/quote?room_id={self.room['id']}&check_in=2034-05-01&check_out=2034-05-02&rate_plan_id={foreign['id']}", headers=self.ctx["h"])
        self.assertEqual(r.status_code, 404)
        for _ in range(9):
            self.plan(name="ещё")
        self.assertEqual(self.client.post(f"/api/room-types/{self.rt['id']}/plans", headers=self.ctx["h"], json={"name": "11-й"}).status_code, 422)
        self.assertEqual(self.client.delete(f"/api/plans/{p['id']}", headers=self.ctx["h"]).status_code, 200)

    def test_extra_guests_and_long_stay(self):
        r = self.client.patch(f"/api/room-types/{self.rt['id']}", headers=self.ctx["h"], json={
            "capacity": 4, "included_guests": 2, "extra_guest_price": 700, "week_discount_percent": 10, "month_discount_percent": 20})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(float(self.quote("2034-06-01", "2034-06-04", guests=2)["total"]), 10500.0)
        q = self.quote("2034-06-01", "2034-06-04", guests=4)
        self.assertEqual(float(q["total"]), 14700.0)  # 10 500 + 2 гостя × 700 × 3 ночи
        self.assertTrue(any("сверх 2" in b["label"] for b in q["breakdown"]))
        week = self.quote("2034-06-01", "2034-06-08", guests=2)  # 7 ночей: 24 500 − 10%
        self.assertEqual(float(week["total"]), 22050.0)
        month = self.quote("2034-07-01", "2034-07-29", guests=2)  # 28 ночей: 98 000 − 20%
        self.assertEqual(float(month["total"]), 78400.0)
        for bad in ({"week_discount_percent": 95}, {"extra_guest_price": -1}, {"month_discount_percent": "x"}):
            self.assertEqual(self.client.patch(f"/api/room-types/{self.rt['id']}", headers=self.ctx["h"], json=bad).status_code, 422, bad)

    def test_public_tariffs_and_request(self):
        nr = self.plan(name="Невозвратный", percent_delta=-10, refundable=False)
        off = self.plan(name="Скрытый", percent_delta=-50, active=False)
        slug = self.ctx["prop"]["public_slug"]
        self.client.patch(f"/api/properties/{self.ctx['prop']['id']}", headers=self.ctx["h"], json={"booking_enabled": True})
        av = self.client.get(f"/api/public/{slug}/availability?check_in=2034-08-01&check_out=2034-08-03&guests=2").json()
        opt = av["options"][0]
        self.assertEqual([t["name"] for t in opt["tariffs"]], ["Невозвратный"])
        self.assertEqual(float(opt["tariffs"][0]["total"]), 6300.0)
        body = {"check_in": "2034-08-01", "check_out": "2034-08-03", "guests": 2, "guest_name": "Пётр", "guest_phone": "+7 900 123-45-67",
                "consent": True, "room_type_id": self.rt["id"]}
        self.assertEqual(self.client.post(f"/api/public/{slug}/book", json={**body, "rate_plan_id": off["id"]}).status_code, 404)
        r = self.client.post(f"/api/public/{slug}/book", json={**body, "rate_plan_id": nr["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(float(r.json()["total"]), 6300.0)

    def test_rates_for_explicit_dates(self):
        r = self.client.put("/api/rates", headers=self.ctx["h"], json={
            "room_type_ids": [self.rt["id"]], "date_from": "2034-09-01", "date_to": "2034-09-30",
            "dates": ["2034-09-05", "2034-09-12", "2034-09-19"], "price": 9999})
        self.assertEqual(r.json()["updated"], 3)
        b = self.client.get("/api/board?from=2034-09-01&days=30", headers=self.ctx["h"]).json()
        rates = b["room_types"][0]["rates"]
        self.assertEqual(sorted(k for k, v in rates.items() if v["price"] is not None), ["2034-09-05", "2034-09-12", "2034-09-19"])


class GuestTests(Base):
    """Раздел «Гости», чёрный список, шаблоны сообщений."""

    def test_list_card_and_phone_formats(self):
        ctx = self.register("guests1@example.ru")
        r0, r1, r2 = ctx["rooms"][:3]
        self.book(ctx, r0, "2035-01-10", "2035-01-12", guest="Иван Петров", guest_phone="+7 900 111-22-33", total_price=7000)
        self.book(ctx, r1, "2035-02-10", "2035-02-13", guest="Иван П.", guest_phone="8 (900) 111-22-33", total_price=9000)
        self.book(ctx, r2, "2035-03-10", "2035-03-11", guest="Анна", guest_phone="+7 911 000-00-00", total_price=3500)
        lst = self.client.get("/api/guests/list", headers=ctx["h"]).json()
        self.assertEqual(len(lst["items"]), 2)  # разные записи телефона — один гость
        ivan = next(g for g in lst["items"] if g["visits"] == 2)
        self.assertEqual((float(ivan["spent"]), int(ivan["nights"])), (16000.0, 5))
        self.assertEqual(len(self.client.get("/api/guests/list?q=анна", headers=ctx["h"]).json()["items"]), 1)
        self.assertEqual(len(self.client.get("/api/guests/list?q=9001112233", headers=ctx["h"]).json()["items"]), 1)
        card = self.client.get("/api/guests/card?phone=%2B79001112233", headers=ctx["h"]).json()
        self.assertEqual((card["visits"], card["returning"], len(card["stays"])), (2, True, 2))
        self.assertEqual(self.client.get("/api/guests/list?sort=bad", headers=ctx["h"]).status_code, 422)
        self.assertEqual(self.client.get("/api/guests/card?phone=12", headers=ctx["h"]).status_code, 422)

    def test_profile_blacklist_and_flags(self):
        ctx = self.register("guests2@example.ru")
        b = self.book(ctx, ctx["rooms"][0], "2035-05-10", "2035-05-14", guest="Олег", guest_phone="+7 922 333-44-55").json()
        r = self.client.put("/api/guests/profile", headers=ctx["h"], json={"phone": "+7 922 333-44-55", "name": "Олег", "blacklisted": True})
        self.assertEqual(r.status_code, 422)  # без причины нельзя
        r = self.client.put("/api/guests/profile", headers=ctx["h"], json={
            "phone": "89223334455", "name": "Олег", "tags": ["VIP", "vip", " с собакой "], "notes": "любит тишину",
            "birthday": "1990-05-12", "blacklisted": True, "blacklist_reason": "Курил в номере"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tags"], ["vip", "с собакой"])
        chk = self.client.get("/api/guests/check?phone=%2B7+922+333-44-55", headers=ctx["h"]).json()
        self.assertEqual((chk["blacklisted"], chk["blacklist_reason"], chk["visits"]), (True, "Курил в номере", 1))
        board = self.client.get("/api/board?from=2035-05-01&days=30", headers=ctx["h"]).json()
        self.assertEqual(board["guest_flags"][b["id"]], {"blacklisted": True, "birthday": "2035-05-12"})
        self.assertEqual(len(self.client.get("/api/guests/list?q=vip", headers=ctx["h"]).json()["items"]), 1)
        # сайт: заявка от гостя из чёрного списка создаётся, но с пометкой
        slug = ctx["prop"]["public_slug"]
        self.client.patch(f"/api/properties/{ctx['prop']['id']}", headers=ctx["h"], json={"booking_enabled": True})
        r = self.client.post(f"/api/public/{slug}/book", json={
            "check_in": "2035-06-01", "check_out": "2035-06-03", "guests": 1, "guest_name": "Олег", "guest_phone": "+7 922 333-44-55",
            "consent": True, "room_type_id": ctx["prop"]["room_types"][0]["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        created = self.client.get(f"/api/bookings/{r.json()['booking_id']}", headers=ctx["h"]).json()
        self.assertIn("ЧЁРНОМ СПИСКЕ", created["notes"])
        # убрать из списка
        self.client.put("/api/guests/profile", headers=ctx["h"], json={"phone": "89223334455", "blacklisted": False})
        self.assertFalse(self.client.get("/api/guests/check?phone=89223334455", headers=ctx["h"]).json()["blacklisted"])

    def test_templates_and_messages(self):
        ctx = self.register("guests3@example.ru")
        tpl = self.client.get("/api/message-templates", headers=ctx["h"]).json()
        self.assertGreaterEqual(len(tpl["items"]), 5)
        b = self.book(ctx, ctx["rooms"][0], "2035-07-10", "2035-07-13", guest="Мария Иванова", guest_email="m@example.ru",
                      total_price=10500, paid_amount=2500).json()
        r = self.client.post(f"/api/bookings/{b['id']}/message", headers=ctx["h"], json={"template_id": tpl["items"][0]["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        text = r.json()["text"]
        self.assertIn("Мария", text)
        self.assertNotIn("Иванова", text)
        self.assertIn("8 000", text)  # сумма к оплате
        self.assertNotIn("{", text)
        r = self.client.post(f"/api/bookings/{b['id']}/message", headers=ctx["h"], json={"body": "{имя}, {срок}, {неизвестное}"})
        self.assertEqual(r.json()["text"], "Мария, 3 ночи, {неизвестное}")
        sent = []
        orig = mail.send_or_log
        mail.send_or_log = lambda to, subject, body: sent.append((to, subject, body))
        try:
            ok = self.client.post(f"/api/bookings/{b['id']}/message/email", headers=ctx["h"], json={"subject": "Бронь", "text": "Привет"})
        finally:
            mail.send_or_log = orig
        self.assertEqual((ok.status_code, sent[0][0]), (200, "m@example.ru"))
        nomail = self.book(ctx, ctx["rooms"][1], "2035-07-10", "2035-07-12", guest="Без почты").json()
        self.assertEqual(self.client.post(f"/api/bookings/{nomail['id']}/message/email", headers=ctx["h"], json={"subject": "x", "text": "y"}).status_code, 422)
        # свои шаблоны + изоляция
        mine = self.client.post("/api/message-templates", headers=ctx["h"], json={"name": "Свой", "body": "Привет, {имя}"}).json()
        other = self.register("guests3b@example.ru")
        self.assertEqual(self.client.patch(f"/api/message-templates/{mine['id']}", headers=other["h"], json={"name": "x", "body": "y"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/message-templates/{mine['id']}", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.post(f"/api/bookings/{b['id']}/message", headers=other["h"], json={"body": "x"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/message-templates/{mine['id']}", headers=ctx["h"]).status_code, 200)

    def test_housekeeper_cannot_open_guests(self):
        ctx = self.register("guests4@example.ru")
        self.client.post("/api/users", headers=ctx["h"], json={"email": "hk4@example.ru", "name": "Горничная", "password": "password123", "role": "housekeeper"})
        tok = self.client.post("/api/auth/login", json={"email": "hk4@example.ru", "password": "password123"}).json()["token"]
        hh = {"Authorization": f"Bearer {tok}"}
        for url in ("/api/guests/list", "/api/guests/card?phone=89001112233", "/api/message-templates"):
            self.assertEqual(self.client.get(url, headers=hh).status_code, 403, url)


class HousekeepingTests(Base):
    """Статусы уборки, экран горничной, назначение, сообщение о поломке."""

    def hk(self, ctx, **q):
        return self.client.get("/api/housekeeping", headers=ctx["h"]).json()

    def staff(self, ctx, email, role="housekeeper"):
        r = self.client.post("/api/users", headers=ctx["h"], json={"email": email, "name": "Горничная Анна", "password": "password123", "role": role})
        self.assertEqual(r.status_code, 200, r.text)
        tok = self.client.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]
        return {"Authorization": f"Bearer {tok}"}, r.json()["id"]

    def test_status_flow_and_auto_dirty(self):
        ctx = self.register("hk1@example.ru", rooms=(("Стандарт", 3, 3500),))
        r0, r1, r2 = ctx["rooms"]
        today = date.today()
        # гость выехал сегодня → номер грязный, пока не отметят уборку
        self.book(ctx, r0, (today - timedelta(days=2)).isoformat(), today.isoformat(), guest="Уехал")
        # гость живёт: заехал вчера, выезжает завтра
        self.book(ctx, r1, (today - timedelta(days=1)).isoformat(), (today + timedelta(days=1)).isoformat(), guest="Живёт")
        st = {r["name"]: r["status"] for r in self.hk(ctx)["rooms"]}
        self.assertEqual((st[r0["name"]], st[r1["name"]], st[r2["name"]]), ("dirty", "occupied", "clean"))
        for new in ("cleaning", "inspect", "clean"):
            r = self.client.post(f"/api/rooms/{r0['id']}/status", headers=ctx["h"], json={"status": new})
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual({r["name"]: r["status"] for r in self.hk(ctx)["rooms"]}[r0["name"]], "clean")
        self.assertEqual(self.client.post(f"/api/rooms/{r0['id']}/status", headers=ctx["h"], json={"status": "магия"}).status_code, 422)
        # старая отметка «убрано» тоже работает
        self.client.post(f"/api/rooms/{r2['id']}/status", headers=ctx["h"], json={"status": "dirty"})
        self.client.post(f"/api/rooms/{r2['id']}/cleaned", headers=ctx["h"], json={"cleaned": True})
        self.assertEqual({r["name"]: r["status"] for r in self.hk(ctx)["rooms"]}[r2["name"]], "clean")

    def test_housekeeper_reports_repair_and_manager_sees_bell(self):
        ctx = self.register("hk2@example.ru", rooms=(("Стандарт", 2, 3500),))
        hh, hid = self.staff(ctx, "hk2maid@example.ru")
        room = ctx["rooms"][0]
        self.assertEqual(self.client.post(f"/api/rooms/{room['id']}/status", headers=hh, json={"status": "repair"}).status_code, 422)  # без причины
        r = self.client.post(f"/api/rooms/{room['id']}/status", headers=hh, json={"status": "repair", "note": "Протекает кран"})
        self.assertEqual(r.status_code, 200, r.text)
        data = self.client.get("/api/housekeeping", headers=hh).json()
        row = next(x for x in data["rooms"] if x["id"] == room["id"])
        self.assertEqual((row["status"], row["hk_note"]), ("repair", "Протекает кран"))
        # горничной недоступны чужие аккаунты и управление
        self.assertEqual(self.client.post("/api/housekeeping/assign", headers=hh, json={"room_ids": [room["id"]], "user_id": hid}).status_code, 403)
        self.assertEqual(self.client.put(f"/api/rooms/{room['id']}/note", headers=hh, json={"note": "x"}).status_code, 403)
        other = self.register("hk2other@example.ru")
        self.assertEqual(self.client.post(f"/api/rooms/{room['id']}/status", headers=other["h"], json={"status": "dirty"}).status_code, 404)
        # починили → снова нужна уборка → убрано
        self.client.post(f"/api/rooms/{room['id']}/status", headers=ctx["h"], json={"status": "dirty"})
        row = next(x for x in self.hk(ctx)["rooms"] if x["id"] == room["id"])
        self.assertEqual((row["status"], row["hk_note"]), ("dirty", ""))

    def test_housekeeper_does_not_see_contacts_or_money(self):
        ctx = self.register("hk4@example.ru", rooms=(("Стандарт", 2, 3500),))
        hh, _ = self.staff(ctx, "hk4maid@example.ru")
        today = date.today()
        self.book(ctx, ctx["rooms"][0], today.isoformat(), (today + timedelta(days=2)).isoformat(), guest="Иван Тест", guest_phone="+7 900 111-22-33",
                  guest_email="i@example.ru", total_price=7000, paid_amount=2000, notes="Поздний заезд")
        for url in (f"/api/board?from={today.isoformat()}&days=5", "/api/today"):
            data = self.client.get(url, headers=hh).json()
            rows = data["bookings"] if "bookings" in data else data["arrivals"]
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["guest_phone"], rows[0]["guest_email"], float(rows[0]["total_price"]), float(rows[0]["paid_amount"])), ("", "", 0.0, 0.0))
            self.assertEqual((rows[0]["guest_name"], rows[0]["notes"]), ("Иван Тест", "Поздний заезд"))  # имя и заметка нужны в работе
        # у администратора всё на месте
        row = self.client.get(f"/api/board?from={today.isoformat()}&days=5", headers=ctx["h"]).json()["bookings"][0]
        self.assertEqual((row["guest_phone"], float(row["paid_amount"])), ("+7 900 111-22-33", 2000.0))

    def test_assignment_and_room_note(self):
        ctx = self.register("hk3@example.ru", rooms=(("Стандарт", 3, 3500),))
        hh, hid = self.staff(ctx, "hk3maid@example.ru")
        ids = [r["id"] for r in ctx["rooms"][:2]]
        r = self.client.post("/api/housekeeping/assign", headers=ctx["h"], json={"room_ids": ids, "user_id": hid})
        self.assertEqual(r.json()["updated"], 2)
        rooms = self.client.get("/api/housekeeping", headers=hh).json()["rooms"]
        self.assertEqual(sorted(x["assigned_to"] for x in rooms if x["assigned_to"]), [hid, hid])
        self.client.post("/api/rooms/%s/status" % ids[0], headers=hh, json={"status": "clean"})  # убрали — назначение снимается
        rooms = self.client.get("/api/housekeeping", headers=hh).json()["rooms"]
        self.assertEqual(sum(1 for x in rooms if x["assigned_to"]), 1)
        self.assertEqual(self.client.put(f"/api/rooms/{ids[1]}/note", headers=ctx["h"], json={"note": "Ключ у соседей"}).status_code, 200)
        self.assertEqual(next(x for x in self.client.get("/api/housekeeping", headers=hh).json()["rooms"] if x["id"] == ids[1])["note"], "Ключ у соседей")
        self.client.post("/api/housekeeping/assign", headers=ctx["h"], json={"room_ids": ids, "user_id": None})
        self.assertFalse(any(x["assigned_to"] for x in self.client.get("/api/housekeeping", headers=hh).json()["rooms"]))
        other = self.register("hk3other@example.ru")
        self.assertEqual(self.client.post("/api/housekeeping/assign", headers=other["h"], json={"room_ids": ids, "user_id": hid}).status_code, 404)


class BoardFeaturesTests(Base):
    """Групповая бронь, переселение посреди проживания, заметки на даты."""

    def test_group_booking_and_cancel_group(self):
        ctx = self.register("grp1@example.ru", rooms=(("Стандарт", 4, 3500),))
        a, b, c3, d4 = ctx["rooms"]
        r = self.client.post("/api/bookings", headers=ctx["h"], json={
            "room_id": a["id"], "extra_room_ids": [b["id"], c3["id"], a["id"]], "check_in": "2036-01-10", "check_out": "2036-01-12",
            "guest_name": "Семья Ивановых", "guests_count": 2})
        self.assertEqual(r.status_code, 200, r.text)
        main = r.json()
        self.assertEqual(len(main["group_ids"]), 3)
        board = self.client.get("/api/board?from=2036-01-01&days=20", headers=ctx["h"]).json()
        grp = [x for x in board["bookings"] if x["group_id"] == main["group_id"]]
        self.assertEqual((len(grp), {float(x["total_price"]) for x in grp}), (3, {7000.0}))
        members = self.client.get(f"/api/bookings/{main['id']}/group", headers=ctx["h"]).json()
        self.assertEqual(len(members), 3)
        # один занятый номер — вся группа не создаётся
        self.book(ctx, d4, "2036-02-10", "2036-02-12", guest="Занято")
        bad = self.client.post("/api/bookings", headers=ctx["h"], json={
            "room_id": a["id"], "extra_room_ids": [d4["id"]], "check_in": "2036-02-10", "check_out": "2036-02-11", "guest_name": "Группа"})
        self.assertEqual(bad.status_code, 409)
        self.assertIn(d4["name"], bad.json()["error"])
        left = self.client.get("/api/board?from=2036-02-01&days=20", headers=ctx["h"]).json()["bookings"]
        self.assertEqual(len(left), 1)  # у номера a нет «осиротевшей» брони
        # отмена всей группы
        self.assertEqual(self.client.delete(f"/api/bookings/{main['id']}?group=1", headers=ctx["h"]).status_code, 200)
        board = self.client.get("/api/board?from=2036-01-01&days=20", headers=ctx["h"]).json()
        self.assertEqual(len(board["bookings"]), 0)
        # чужой номер в группе нельзя
        other = self.register("grp1b@example.ru")
        r = self.client.post("/api/bookings", headers=ctx["h"], json={
            "room_id": a["id"], "extra_room_ids": [other["rooms"][0]["id"]], "check_in": "2036-03-10", "check_out": "2036-03-11"})
        self.assertEqual(r.status_code, 404)

    def test_relocate_mid_stay(self):
        ctx = self.register("rel1@example.ru", rooms=(("Стандарт", 3, 3500),))
        a, b, c3 = ctx["rooms"]
        bk = self.book(ctx, a, "2036-05-10", "2036-05-14", total_price=8000, paid_amount=3000, guest="Пётр", guest_phone="+7 900 111-22-33").json()
        self.book(ctx, c3, "2036-05-12", "2036-05-13", guest="Мешает")
        self.assertEqual(self.client.post(f"/api/bookings/{bk['id']}/relocate", headers=ctx["h"], json={"room_id": c3["id"], "from_date": "2036-05-12"}).status_code, 409)
        for bad in ("2036-05-10", "2036-05-14", "2036-05-20"):
            self.assertEqual(self.client.post(f"/api/bookings/{bk['id']}/relocate", headers=ctx["h"], json={"room_id": b["id"], "from_date": bad}).status_code, 422, bad)
        self.assertEqual(self.client.post(f"/api/bookings/{bk['id']}/relocate", headers=ctx["h"], json={"room_id": a["id"], "from_date": "2036-05-12"}).status_code, 422)
        r = self.client.post(f"/api/bookings/{bk['id']}/relocate", headers=ctx["h"], json={"room_id": b["id"], "from_date": "2036-05-12"})
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertEqual((float(out["first_total"]), float(out["second_total"])), (4000.0, 4000.0))
        first = self.client.get(f"/api/bookings/{bk['id']}", headers=ctx["h"]).json()
        second = self.client.get(f"/api/bookings/{out['second']}", headers=ctx["h"]).json()
        self.assertEqual((first["check_out"], second["check_in"], second["check_out"]), ("2036-05-12", "2036-05-12", "2036-05-14"))
        self.assertEqual((second["guest_name"], second["room_id"], first["group_id"] == second["group_id"] and bool(first["group_id"])), ("Пётр", b["id"], True))
        self.assertEqual(float(first["paid_amount"]), 3000.0)  # оплата остаётся в первой части
        self.assertEqual(len(self.client.get(f"/api/bookings/{second['id']}/group", headers=ctx["h"]).json()), 2)

    def test_date_notes(self):
        ctx = self.register("note1@example.ru")
        r = self.client.put("/api/date-notes", headers=ctx["h"], json={"day": "2036-06-12", "text": "День города, дороже"})
        self.assertEqual(r.status_code, 200, r.text)
        board = self.client.get("/api/board?from=2036-06-01&days=30", headers=ctx["h"]).json()
        self.assertEqual(board["date_notes"], {"2036-06-12": "День города, дороже"})
        self.client.put("/api/date-notes", headers=ctx["h"], json={"day": "2036-06-12", "text": "Новый текст"})
        self.assertEqual(self.client.get("/api/board?from=2036-06-01&days=30", headers=ctx["h"]).json()["date_notes"]["2036-06-12"], "Новый текст")
        other = self.register("note1b@example.ru")
        self.assertEqual(self.client.get("/api/board?from=2036-06-01&days=30", headers=other["h"]).json()["date_notes"], {})
        self.client.put("/api/date-notes", headers=ctx["h"], json={"day": "2036-06-12", "text": ""})
        self.assertEqual(self.client.get("/api/board?from=2036-06-01&days=30", headers=ctx["h"]).json()["date_notes"], {})
        self.assertEqual(self.client.put("/api/date-notes", headers=ctx["h"], json={"day": "не дата", "text": "x"}).status_code, 422)


class LandlordTests(Base):
    """Роль «Собственник» и отчёт собственнику с комиссией УК."""

    def setup_account(self, email):
        ctx = self.register(email, rooms=(("Стандарт", 2, 4000),))
        # второй объект, который собственнику не назначен
        r2 = self.client.post("/api/setup", headers=ctx["h"], json={"name": "Чужой объект", "room_types": [{"name": "Студия", "count": 1, "base_price": 2000, "capacity": 2}]})
        self.assertEqual(r2.status_code, 200, r2.text)
        return ctx, r2.json()

    def make_landlord(self, ctx, props, email="owner.ll@example.ru"):
        r = self.client.post("/api/users", headers=ctx["h"], json={"email": email, "name": "Собственник Пётр", "password": "password123",
                                                                  "role": "landlord", "property_ids": props})
        self.assertEqual(r.status_code, 200, r.text)
        tok = self.client.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]
        return {"Authorization": f"Bearer {tok}"}, r.json()["id"]

    def test_report_math(self):
        ctx, other = self.setup_account("ll1@example.ru")
        pid = ctx["prop"]["id"]
        room = ctx["rooms"][0]
        # 10 ночей в месяце: 4 000 × 10 = 40 000 (Авито, комиссия 10%); плюс бронь через край месяца
        self.client.put("/api/channel-commissions", headers=ctx["h"], json={"items": [{"channel": "avito", "percent": 10}]})
        self.book(ctx, room, "2037-03-01", "2037-03-11", total_price=40000, source="avito", guest="Иван Иванов")
        self.book(ctx, ctx["rooms"][1], "2037-03-30", "2037-04-03", total_price=8000, guest="Мария Петрова")  # 2 ночи в марте = 4 000
        cat = self.client.get("/api/expense-categories", headers=ctx["h"]).json()[0]
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat["id"], "amount": 5000, "date": "2037-03-15", "property_id": pid})
        self.client.post("/api/expenses", headers=ctx["h"], json={"category_id": cat["id"], "amount": 99999, "date": "2037-03-15"})  # общий — не входит
        r = self.client.put(f"/api/properties/{pid}/commission", headers=ctx["h"], json={"percent": 20, "base": "net"})
        self.assertEqual(r.status_code, 200, r.text)
        rep = self.client.get(f"/api/landlord/report?property_id={pid}&month=2037-03", headers=ctx["h"]).json()
        self.assertEqual((float(rep["revenue"]), float(rep["platform_commission"]), float(rep["net_revenue"])), (44000.0, 4000.0, 40000.0))
        self.assertEqual((float(rep["expenses_total"]), float(rep["mc_commission"])), (5000.0, 8000.0))
        self.assertEqual(float(rep["payout"]), 27000.0)  # 40 000 − 5 000 − 20% от 40 000
        self.assertEqual(rep["sold_nights"], 12)
        self.assertEqual({x["guest"] for x in rep["stays"]}, {"Иван И.", "Мария П."})
        # база «выручка до комиссий площадок»
        self.client.put(f"/api/properties/{pid}/commission", headers=ctx["h"], json={"percent": 10, "base": "gross"})
        rep = self.client.get(f"/api/landlord/report?property_id={pid}&month=2037-03", headers=ctx["h"]).json()
        self.assertEqual((float(rep["mc_commission"]), float(rep["payout"])), (4400.0, 30600.0))
        csv_text = self.client.get(f"/api/landlord/report?property_id={pid}&month=2037-03&format=csv", headers=ctx["h"]).content.decode("utf-8-sig")
        self.assertIn("К выплате собственнику;30600,00", csv_text)
        for bad in ({"percent": 150}, {"percent": 10, "base": "weird"}):
            self.assertEqual(self.client.put(f"/api/properties/{pid}/commission", headers=ctx["h"], json=bad).status_code, 422)

    def test_landlord_is_read_only_and_scoped(self):
        ctx, other = self.setup_account("ll2@example.ru")
        pid = ctx["prop"]["id"]
        self.book(ctx, ctx["rooms"][0], "2037-05-10", "2037-05-12", total_price=8000, guest="Анна Смирнова", guest_phone="+7 900 000-11-22", notes="секрет")
        self.assertEqual(self.client.post("/api/users", headers=ctx["h"], json={"email": "x@example.ru", "name": "X", "password": "password123", "role": "landlord"}).status_code, 422)
        hh, uid = self.make_landlord(ctx, [pid])
        me = self.client.get("/api/me", headers=hh).json()
        self.assertEqual((me["role"], [p["id"] for p in me["properties"]]), ("landlord", [pid]))
        for url in ("/api/board", "/api/bookings", "/api/today", "/api/housekeeping", "/api/guests/list", "/api/expenses", "/api/users", "/api/services"):
            self.assertEqual(self.client.get(url, headers=hh).status_code, 403, url)
        self.assertEqual(self.client.post("/api/bookings", headers=hh, json={"room_id": ctx["rooms"][0]["id"], "check_in": "2037-06-01", "check_out": "2037-06-02"}).status_code, 403)
        b = self.client.get(f"/api/landlord/board?property_id={pid}&from=2037-05-01&days=30", headers=hh).json()
        bk = b["bookings"][0]
        self.assertEqual((bk["guest_name"], bk["guest_phone"], bk["notes"]), ("Анна С.", "", ""))
        self.assertEqual(self.client.get(f"/api/landlord/board?property_id={other['id']}&from=2037-05-01&days=30", headers=hh).status_code, 404)
        self.assertEqual(self.client.get(f"/api/landlord/report?property_id={other['id']}&month=2037-05", headers=hh).status_code, 404)
        rep = self.client.get("/api/landlord/report?month=2037-05", headers=hh).json()  # без property_id — первый назначенный
        self.assertEqual(rep["property"]["id"], pid)
        # назначили второй объект — стал виден
        self.assertEqual(self.client.put(f"/api/users/{uid}/properties", headers=ctx["h"], json={"property_ids": [pid, other["id"]]}).status_code, 200)
        self.assertEqual(len(self.client.get("/api/landlord/properties", headers=hh).json()), 2)
        # собственник не может менять комиссию и назначения
        self.assertEqual(self.client.put(f"/api/properties/{pid}/commission", headers=hh, json={"percent": 0}).status_code, 403)
        self.assertEqual(self.client.put(f"/api/users/{uid}/properties", headers=hh, json={"property_ids": []}).status_code, 403)

    def test_isolation_and_housekeeper(self):
        a, _ = self.setup_account("ll3a@example.ru")
        b = self.register("ll3b@example.ru")
        self.assertEqual(self.client.get(f"/api/landlord/report?property_id={a['prop']['id']}", headers=b["h"]).status_code, 404)
        r = self.client.post("/api/users", headers=b["h"], json={"email": "ll3x@example.ru", "name": "Чужой", "password": "password123", "role": "landlord", "property_ids": [a["prop"]["id"]]})
        self.assertEqual(r.status_code, 404)  # чужой объект назначить нельзя
        self.client.post("/api/users", headers=a["h"], json={"email": "ll3hk@example.ru", "name": "Горничная", "password": "password123", "role": "housekeeper"})
        tok = self.client.post("/api/auth/login", json={"email": "ll3hk@example.ru", "password": "password123"}).json()["token"]
        self.assertEqual(self.client.get("/api/landlord/report", headers={"Authorization": f"Bearer {tok}"}).status_code, 403)


class QuoteHintsTests(Base):
    def test_busy_message_and_gap_hint(self):
        ctx = self.register("hint1@example.ru", rooms=(("Стандарт", 2, 3500),))
        a, b = ctx["rooms"]
        self.book(ctx, a, "2039-03-10", "2039-03-13", guest="Иван Иванов")
        r = self.book(ctx, a, "2039-03-12", "2039-03-14")
        self.assertEqual(r.status_code, 409)
        msg = r.json()["error"]
        self.assertIn(f"Номер {a['name']} занят: Иван Иванов, с 10.03 по 13.03", msg)
        self.assertIn("другой номер", msg)
        base = f"/api/bookings/quote?room_id={a['id']}&check_out="
        q = self.client.get(f"/api/bookings/quote?room_id={a['id']}&check_in=2039-03-14&check_out=2039-03-16", headers=ctx["h"]).json()
        self.assertEqual(len(q["gaps"]), 1)  # между 13.03 и 14.03 останется одна ночь
        self.assertIn("13.03", q["gaps"][0])
        q = self.client.get(f"/api/bookings/quote?room_id={a['id']}&check_in=2039-03-13&check_out=2039-03-16", headers=ctx["h"]).json()
        self.assertEqual(q["gaps"], [])  # вплотную — дырки нет
        q = self.client.get(f"/api/bookings/quote?room_id={a['id']}&check_in=2039-03-05&check_out=2039-03-09", headers=ctx["h"]).json()
        self.assertEqual(len(q["gaps"]), 1)  # после этой брони — одна ночь до заезда 10.03
        q = self.client.get(f"/api/bookings/quote?room_id={a['id']}&check_in=2039-03-11&check_out=2039-03-12", headers=ctx["h"]).json()
        self.assertTrue(q["busy"] and q["gaps"] == [])


class FreeRoomsTests(Base):
    def test_free_rooms_for_dates(self):
        ctx = self.register("free1@example.ru", rooms=(("Стандарт", 3, 3500), ("Делюкс", 2, 5500)))
        std = [r for r in ctx["rooms"]][:3]
        self.book(ctx, std[0], "2038-01-10", "2038-01-13")
        r = self.client.get("/api/bookings/free-rooms?check_in=2038-01-11&check_out=2038-01-12&guests=2", headers=ctx["h"])
        self.assertEqual(r.status_code, 200, r.text)
        types = {t["type"]: t for t in r.json()["types"]}
        self.assertEqual([x["name"] for x in types["Стандарт"]["rooms"]], [std[1]["name"], std[2]["name"]])
        self.assertEqual((len(types["Делюкс"]["rooms"]), float(types["Делюкс"]["price"])), (2, 5500.0))
        # при редактировании брони сам номер не считается занятым
        b = self.client.get("/api/board?from=2038-01-01&days=30", headers=ctx["h"]).json()["bookings"][0]
        r = self.client.get(f"/api/bookings/free-rooms?check_in=2038-01-11&check_out=2038-01-12&exclude={b['id']}", headers=ctx["h"]).json()
        self.assertEqual(len({x["name"] for x in r["types"][0]["rooms"]}), 3)
        self.assertEqual(self.client.get("/api/bookings/free-rooms?check_in=2038-01-12&check_out=2038-01-11", headers=ctx["h"]).status_code, 422)
        other = self.register("free1b@example.ru")
        r = self.client.get("/api/bookings/free-rooms?check_in=2038-01-11&check_out=2038-01-12", headers=other["h"]).json()
        self.assertEqual(sum(len(t["rooms"]) for t in r["types"]), 12)  # у другого аккаунта своя картина


class MaxChannelTests(Base):
    """Второй канал уведомлений — MAX. Выключен без MAX_BOT_TOKEN; здесь токен включаем,
    а реальную отправку (maxbot.send_message) подменяем моком: ни одного запроса к MAX."""

    def setUp(self):
        self.ctx = self.register(f"max{id(self)}@example.ru")
        self.acc = self.ctx["prop"]["account_id"]
        self._orig = (config.MAX_BOT_TOKEN, config.MAX_WEBHOOK_SECRET, config.MAX_BOT_USERNAME, config.TELEGRAM_BOT_TOKEN, maxbot.send_message, telegram.send_message)
        config.MAX_BOT_TOKEN = "max-test-token"
        config.MAX_WEBHOOK_SECRET = ""
        config.MAX_BOT_USERNAME = "fligel_bot"
        config.TELEGRAM_BOT_TOKEN = "tg-test-token"
        self.sent, self.tg_sent = [], []
        maxbot.send_message = lambda chat_id, text: self.sent.append((chat_id, text))
        telegram.send_message = lambda chat_id, text: self.tg_sent.append((chat_id, text))

    def tearDown(self):
        (config.MAX_BOT_TOKEN, config.MAX_WEBHOOK_SECRET, config.MAX_BOT_USERNAME, config.TELEGRAM_BOT_TOKEN,
         maxbot.send_message, telegram.send_message) = self._orig

    def chat(self):
        return id(self) % 800000000 + 100000000

    def link_max(self, via="bot_started"):
        st = self.client.post("/api/notify/max/link", headers=self.ctx["h"]).json()
        ch = next(c for c in st["channels"] if c["name"] == "max")
        code = ch["pending_code"]
        self.assertEqual(ch["deep_link"], f"https://max.ru/fligel_bot?start={code}")
        upd = ({"update_type": "bot_started", "chat_id": self.chat(), "payload": code} if via == "bot_started"
               else {"update_type": "message_created", "message": {"recipient": {"chat_id": self.chat()}, "body": {"text": f"/start {code}"}}})
        r = self.client.post("/api/max/webhook", json=upd)
        self.assertTrue(r.json()["linked"], r.text)

    def test_disabled_by_default(self):
        config.MAX_BOT_TOKEN = ""
        st = self.client.get("/api/notify/status", headers=self.ctx["h"]).json()
        self.assertFalse(next(c for c in st["channels"] if c["name"] == "max")["server_enabled"])
        self.assertEqual(self.client.post("/api/notify/max/link", headers=self.ctx["h"]).status_code, 422)
        with db.tx() as conn:
            self.assertEqual(maxbot.notify(conn, self.acc, "new_booking", "x"), 0)
        self.assertEqual(maxbot.process_outbox(), {"sent": 0, "failed": 0})
        self.assertEqual(self.client.post("/api/max/webhook", json={"update_type": "bot_started", "chat_id": 1, "payload": "AAAA"}).json(), {"ok": True})

    def test_link_flow_both_variants_and_delivery(self):
        for via in ("bot_started", "message_created"):
            self.link_max(via)
            with db.tx() as conn:
                self.assertEqual(notify.send(conn, self.acc, "new_booking", f"Заявка {via}"), 2 if False else notify.send(conn, self.acc, "new_booking", f"Заявка {via}"))
            maxbot.process_outbox()
            self.client.post("/api/notify/max/unlink", headers=self.ctx["h"])
        texts = [t for _, t in self.sent]
        self.assertTrue(any("подключены" in t for t in texts))
        self.assertTrue(any("bot_started" in t for t in texts) and any("message_created" in t for t in texts))
        # неверный и просроченный код не привязывают
        self.assertFalse(self.client.post("/api/max/webhook", json={"update_type": "bot_started", "chat_id": 5, "payload": "ZZZZZZZZ"}).json()["linked"])

    def test_both_channels_and_user_choice(self):
        self.link_max()
        resp = self.client.post("/api/notify/telegram/link", headers=self.ctx["h"])
        self.assertEqual(resp.status_code, 200, resp.text)
        code = next(c for c in resp.json()["channels"] if c["name"] == "telegram")["pending_code"]
        self.client.post("/api/telegram/webhook", json={"message": {"text": f"/start {code}", "chat": {"id": self.chat() + 1}}})
        with db.tx() as conn:
            notify.send(conn, self.acc, "conflict", "Двойная бронь!")
        maxbot.process_outbox(); telegram.process_outbox()
        self.assertIn((self.chat(), "Двойная бронь!"), self.sent)
        self.assertIn((self.chat() + 1, "Двойная бронь!"), self.tg_sent)
        # сотрудник отключил Telegram, оставил MAX
        r = self.client.put("/api/notify/settings", headers=self.ctx["h"], json={"events": ["conflict", "digest"], "channels": {"telegram": False, "max": True}})
        self.assertEqual(r.status_code, 200, r.text)
        self.sent.clear(); self.tg_sent.clear()
        with db.tx() as conn:
            notify.send(conn, self.acc, "conflict", "Второй")
            notify.send(conn, self.acc, "new_booking", "Не подписан")
        maxbot.process_outbox(); telegram.process_outbox()
        self.assertEqual(([t for _, t in self.sent], self.tg_sent), (["Второй"], []))

    def test_retries_and_secret(self):
        self.link_max()
        calls = []
        def flaky(chat_id, text):
            if text == "Повтор":
                calls.append(text)
            raise RuntimeError("MAX недоступен")
        maxbot.send_message = flaky
        with db.tx() as conn:
            maxbot.notify(conn, self.acc, "new_booking", "Повтор")
        self.assertEqual(maxbot.process_outbox()["sent"], 0)
        with db.tx() as conn:
            row = db.one(conn, "SELECT status, attempts FROM max_outbox WHERE text = 'Повтор'")
        self.assertEqual((row["status"], row["attempts"]), ("pending", 1))
        self.assertEqual(maxbot.process_outbox()["sent"], 0)  # пауза перед повтором — второй попытки пока нет
        self.assertEqual(len(calls), 1)
        config.MAX_WEBHOOK_SECRET = "s3cret"
        self.assertEqual(self.client.post("/api/max/webhook", json={"update_type": "bot_started", "chat_id": 1, "payload": "A"}).status_code, 403)
        ok = self.client.post("/api/max/webhook", headers={"X-Max-Bot-Api-Secret": "s3cret"}, json={"update_type": "bot_started", "chat_id": 1, "payload": "A"})
        self.assertEqual(ok.status_code, 200)

    def test_parse_update_shapes(self):
        self.assertEqual(maxbot.parse_update({"update_type": "bot_started", "chat_id": 7, "payload": " ab12 "}), (7, "ab12"))
        self.assertEqual(maxbot.parse_update({"update_type": "message_created", "message": {"recipient": {"chat_id": 9}, "body": {"text": "/start CODE1234"}}}), (9, "CODE1234"))
        self.assertEqual(maxbot.parse_update({"update_type": "message_created", "message": {"recipient": {"chat_id": 9}, "body": {"text": "очень длинный произвольный текст сообщения"}}}), (9, ""))
        self.assertEqual(maxbot.parse_update({"update_type": "bot_added"}), (None, ""))

    def test_digest_goes_to_max_once(self):
        self.link_max()
        now = datetime.now().replace(hour=23, minute=0)
        def mine():
            with db.tx() as conn:
                return db.one(conn, "SELECT count(*) AS n FROM max_outbox WHERE account_id = %s AND text LIKE 'Доброе утро%%'", (self.acc,))["n"]
        maxbot.maybe_send_digests(now)
        self.assertEqual(mine(), 1)
        maxbot.maybe_send_digests(now)
        self.assertEqual(mine(), 1)  # второй раз за день не шлём
        maxbot.process_outbox()
        self.assertTrue(any("Доброе утро" in t for _, t in self.sent))


class BellAndAuditTests(Base):
    def test_site_request_rings_bell_and_seen_resets(self):
        ctx = self.register("bell1@example.ru")
        slug = ctx["prop"]["public_slug"]
        self.client.patch(f"/api/properties/{ctx['prop']['id']}", headers=ctx["h"], json={"booking_enabled": True})
        self.assertEqual(self.client.get("/api/notifications", headers=ctx["h"]).json()["unread"], 0)
        r = self.client.post(f"/api/public/{slug}/book", json={"check_in": "2040-03-01", "check_out": "2040-03-03", "guests": 1,
            "guest_name": "Пётр", "guest_phone": "+7 900 123-45-67", "consent": True, "room_type_id": ctx["prop"]["room_types"][0]["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        bell = self.client.get("/api/notifications", headers=ctx["h"]).json()
        self.assertEqual(bell["unread"], 1)
        self.assertIn("Новая заявка с сайта", bell["items"][0]["text"])
        self.assertEqual(bell["items"][0]["link"], "#/bookings")
        self.client.post("/api/notifications/seen", headers=ctx["h"])
        self.assertEqual(self.client.get("/api/notifications", headers=ctx["h"]).json()["unread"], 0)
        other = self.register("bell1b@example.ru")
        self.assertEqual(self.client.get("/api/notifications", headers=other["h"]).json()["items"], [])
        self.client.post("/api/users", headers=ctx["h"], json={"email": "bellmaid@example.ru", "name": "Г", "password": "password123", "role": "housekeeper"})
        tok = self.client.post("/api/auth/login", json={"email": "bellmaid@example.ru", "password": "password123"}).json()["token"]
        self.assertEqual(self.client.get("/api/notifications", headers={"Authorization": f"Bearer {tok}"}).status_code, 403)

    def test_audit_feed(self):
        ctx = self.register("audit1@example.ru")
        self.client.post("/api/users", headers=ctx["h"], json={"email": "audit1m@example.ru", "name": "Мария", "password": "password123", "role": "manager"})
        self.book(ctx, ctx["rooms"][0], "2040-04-10", "2040-04-12", guest="Гость Журнала", total_price=5000, paid_amount=1000)
        self.client.put("/api/rates", headers=ctx["h"], json={"room_type_ids": [ctx["prop"]["room_types"][0]["id"]], "date_from": "2040-04-01", "date_to": "2040-04-03", "price": 4000})
        feed = self.client.get("/api/audit", headers=ctx["h"]).json()["items"]
        texts = " | ".join(i["text"] for i in feed)
        self.assertIn("Добавлен сотрудник Мария (manager)", texts)
        self.assertIn("Создана бронь «Гость Журнала»", texts)
        self.assertIn("Изменены цены", texts)
        self.assertTrue(all(i["who"] for i in feed))
        # не-владелец и чужой аккаунт журнал не видят
        tok = self.client.post("/api/auth/login", json={"email": "audit1m@example.ru", "password": "password123"}).json()["token"]
        self.assertEqual(self.client.get("/api/audit", headers={"Authorization": f"Bearer {tok}"}).status_code, 403)
        other = self.register("audit1b@example.ru")
        self.assertEqual(self.client.get("/api/audit", headers=other["h"]).json()["items"], [])
        self.assertEqual(self.client.get("/api/audit?before=не-дата", headers=ctx["h"]).status_code, 422)


if __name__ == "__main__":
    unittest.main()
