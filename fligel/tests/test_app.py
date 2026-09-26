"""Сквозные тесты API на настоящей PostgreSQL.

Запуск:  DATABASE_URL=postgresql://postgres@127.0.0.1/fligel_test python -m unittest discover -s tests -v
Тестовая база пересоздаётся при каждом запуске.
"""
import os
import threading
import unittest
from datetime import date, timedelta
from urllib.parse import urlparse

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/fligel_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ["SYNC_ENABLED"] = "0"
os.environ["PUBLIC_BASE_URL"] = "https://fligel.test"
os.environ["SECRET_KEY"] = "test-secret"

import psycopg  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import db, expenses, ical, sync  # noqa: E402
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
        self.assertEqual(self.client.get("/api/stats", headers=h).status_code, 403)


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
        s = self.client.get("/api/stats", headers=ctx["h"], params={"from": d(0), "days": 10}).json()
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
        stats1 = self.client.get("/api/stats", headers=ctx["h"],
                                  params={"property_id": ctx["prop"]["id"], "from": d(0), "days": 2}).json()
        self.assertEqual(stats1["rooms"], 1)
        self.assertEqual(float(stats1["revenue"]), 6000)
        stats_all = self.client.get("/api/stats", headers=ctx["h"], params={"from": d(0), "days": 2}).json()
        self.assertEqual(stats_all["rooms"], 2)
        self.assertEqual(float(stats_all["revenue"]), 10000)
        bookings_all = self.client.get("/api/bookings", headers=ctx["h"], params={"from": d(0)}).json()
        self.assertEqual(len(bookings_all), 2)
        bookings1 = self.client.get("/api/bookings", headers=ctx["h"],
                                     params={"from": d(0), "property_id": ctx["prop"]["id"]}).json()
        self.assertEqual(len(bookings1), 1)


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


if __name__ == "__main__":
    unittest.main()
