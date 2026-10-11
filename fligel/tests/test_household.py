"""Раунд 5, этап 3: хозяйство — склад расходников, счётчики с автоматическим расходом, инвентарь и проверка после выезда."""
import unittest
from decimal import Decimal

from test_app import Base, d  # noqa: F401

from app import db


class Mixin:
    def staff(self, ctx, email, role="housekeeper", name="Мария"):
        r = self.client.post("/api/users", headers=ctx["h"], json={"name": name, "email": email, "role": role, "password": "password123"})
        self.assertEqual(r.status_code, 200, r.text)
        tok = self.client.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]
        return {"id": r.json()["id"], "h": {"Authorization": f"Bearer {tok}"}}

    def item(self, ctx, name="Шампунь", **kw):
        r = self.client.post("/api/stock/items", headers=ctx["h"], json={"name": name, "unit": "шт", "quantity": 10, "min_quantity": 3, "norm_per_cleaning": 1, **kw})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def stock(self, ctx, h=None):
        return {i["name"]: i for i in self.client.get("/api/stock", headers=h or ctx["h"]).json()["items"]}


class StockTests(Mixin, Base):
    def test_moves_validation_history_and_low_stock_alert_once_a_day(self):
        ctx = self.register("st1@example.ru")
        it = self.item(ctx)
        self.assertEqual(float(it["quantity"]), 10.0)
        mv = lambda kind, amount, **kw: self.client.post(f"/api/stock/items/{it['id']}/move", headers=ctx["h"], json={"kind": kind, "amount": amount, **kw})
        self.assertEqual(float(mv("in", 5, note="Закупка").json()["quantity"]), 15.0)
        self.assertEqual(float(mv("out", 4).json()["quantity"]), 11.0)
        r = mv("out", 50)
        self.assertEqual(r.status_code, 422)
        self.assertIn("На складе только 11", r.json()["error"])
        self.assertEqual(mv("out", 0).status_code, 422)
        self.assertEqual(mv("burn", 1).status_code, 422)
        notes = lambda: [n["text"] for n in self.client.get("/api/notifications", headers=ctx["h"]).json()["items"] if "Заканчивается" in n["text"]]
        self.assertEqual(notes(), [])
        self.assertEqual(float(mv("writeoff", 8, note="Протекла упаковка").json()["quantity"]), 3.0)
        self.assertEqual(len(notes()), 1)
        self.assertIn("Шампунь", notes()[0])
        mv("out", 1)
        self.assertEqual(len(notes()), 1)                      # в тот же день повторно не пишем
        self.assertTrue(self.stock(ctx)["Шампунь"]["low"])
        # приход выше минимума снимает отметку, и следующее падение снова сообщит
        mv("in", 10)
        self.assertFalse(self.stock(ctx)["Шампунь"]["low"])
        mv("out", 9)
        self.assertEqual(len(notes()), 2)
        # инвентаризация: «на самом деле 7»
        self.assertEqual(float(mv("correction", 7).json()["quantity"]), 7.0)
        hist = self.client.get(f"/api/stock/items/{it['id']}/history", headers=ctx["h"]).json()["moves"]
        self.assertEqual([m["kind"] for m in hist][:2], ["correction", "out"])
        self.assertEqual(hist[-1]["note"], "Начальный остаток")

    def test_roles_and_account_isolation(self):
        ctx = self.register("st2@example.ru")
        other = self.register("st2b@example.ru")
        maid = self.staff(ctx, "maid-st2@example.ru")
        it = self.item(ctx)
        base = f"/api/stock/items/{it['id']}/move"
        self.assertEqual(self.client.post(base, headers=maid["h"], json={"kind": "out", "amount": 1}).status_code, 200)      # горничная берёт расходник
        self.assertEqual(self.client.post(base, headers=maid["h"], json={"kind": "in", "amount": 1}).status_code, 403)
        self.assertEqual(self.client.post(base, headers=maid["h"], json={"kind": "writeoff", "amount": 1}).status_code, 403)
        self.assertEqual(self.client.post("/api/stock/items", headers=maid["h"], json={"name": "X"}).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/stock/items/{it['id']}", headers=maid["h"], json={"name": "Y"}).status_code, 403)
        self.assertEqual(len(self.client.get("/api/stock", headers=maid["h"]).json()["items"]), 1)
        self.assertFalse(self.client.get("/api/stock", headers=maid["h"]).json()["can_edit"])
        # чужой аккаунт
        self.assertEqual(self.stock(other), {})
        self.assertEqual(self.client.post(base, headers=other["h"], json={"kind": "out", "amount": 1}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/stock/items/{it['id']}/history", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/stock/items/{it['id']}", headers=other["h"], json={"name": "Взлом"}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/stock?property_id={ctx['prop']['id']}", headers=other["h"]).status_code, 404)

    def test_cleaning_writes_off_by_norm_once_per_day_and_clamps_at_zero(self):
        ctx = self.register("st3@example.ru")
        maid = self.staff(ctx, "maid-st3@example.ru")
        soap = self.item(ctx, "Мыло", quantity=10, min_quantity=0, norm_per_cleaning=2)
        bags = self.item(ctx, "Пакеты", quantity=1, min_quantity=0, norm_per_cleaning=3)       # на складе меньше нормы
        self.item(ctx, "Свечи", quantity=5, norm_per_cleaning=0)                                # без нормы — не трогаем
        r1, r2 = ctx["rooms"][:2]
        clean = lambda room: self.client.post(f"/api/rooms/{room['id']}/status", headers=maid["h"], json={"status": "clean"})
        self.assertEqual(clean(r1).status_code, 200)
        clean(r1)                                                                                # повторная отметка в тот же день
        st = self.stock(ctx)
        self.assertEqual(float(st["Мыло"]["quantity"]), 8.0)
        self.assertEqual(float(st["Пакеты"]["quantity"]), 0.0)                                   # списали сколько было, без ошибки
        self.assertEqual(float(st["Свечи"]["quantity"]), 5.0)
        # второй номер — через кнопку «Убрать» на экране «Сегодня»
        self.assertEqual(self.client.post(f"/api/rooms/{r2['id']}/cleaned", headers=maid["h"], json={"cleaned": True}).status_code, 200)
        self.client.post(f"/api/rooms/{r2['id']}/cleaned", headers=maid["h"], json={"cleaned": True})
        self.assertEqual(float(self.stock(ctx)["Мыло"]["quantity"]), 6.0)
        hist = self.client.get(f"/api/stock/items/{soap['id']}/history", headers=ctx["h"]).json()["moves"]
        self.assertEqual([m["kind"] for m in hist if m["kind"] == "cleaning"], ["cleaning", "cleaning"])
        self.assertIn("Уборка номера", hist[0]["note"])
        self.assertEqual(bags["name"], "Пакеты")


class MeterTests(Mixin, Base):
    def meter(self, ctx, **kw):
        r = self.client.post("/api/meters", headers=ctx["h"], json={"kind": "water_cold", "tariff": 40, "room_id": ctx["rooms"][0]["id"], **kw})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def reading(self, ctx, mid, value, day=None, **kw):
        return self.client.post(f"/api/meters/{mid}/readings", headers=ctx["h"], json={"value": value, "date": day or d(0), **kw})

    def expenses(self, ctx):
        r = self.client.get(f"/api/expenses?from={d(-60)}&to={d(2)}", headers=ctx["h"])
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["rows"]

    def test_readings_consumption_cost_and_automatic_expense(self):
        ctx = self.register("mt1@example.ru")
        mid = self.meter(ctx)
        first = self.reading(ctx, mid, 100, d(-30))
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual((float(first.json()["consumption"]), float(first.json()["cost"]), first.json()["expense_id"]), (0.0, 0.0, None))   # первое показание — точка отсчёта
        second = self.reading(ctx, mid, 112.5, d(0))
        self.assertEqual((float(second.json()["consumption"]), float(second.json()["cost"])), (12.5, 500.0))
        items = self.expenses(ctx)
        self.assertEqual(len(items), 1)
        self.assertEqual(float(items[0]["amount"]), 500.0)
        self.assertEqual(items[0]["room_id"], ctx["rooms"][0]["id"])
        self.assertIn("12,5", items[0]["comment"])
        self.assertEqual(items[0]["date"], d(0))
        # тариф поменяли — прежние показания не пересчитываются, новое считается по новому
        self.client.patch(f"/api/meters/{mid}", headers=ctx["h"], json={"tariff": 50})
        third = self.reading(ctx, mid, 122.5, d(0))
        self.assertEqual((float(third.json()["consumption"]), float(third.json()["cost"])), (10.0, 500.0))
        lst = self.client.get("/api/meters", headers=ctx["h"]).json()["meters"][0]
        self.assertEqual(float(lst["last"]["value"]), 122.5)
        self.assertEqual(lst["label"], "Холодная вода")
        self.assertEqual(float(sum(Decimal(str(m["consumption"])) for m in lst["monthly"])), 22.5)

    def test_validation_replacement_and_deleting_last_reading_removes_expense(self):
        ctx = self.register("mt2@example.ru")
        mid = self.meter(ctx, kind="electricity", tariff=6.5)
        self.reading(ctx, mid, 5000, d(-20))
        self.assertEqual(self.reading(ctx, mid, 4000, d(-10)).status_code, 422)               # меньше предыдущего
        self.assertEqual(self.reading(ctx, mid, 5100, d(-25)).status_code, 422)               # дата раньше предыдущего
        self.assertEqual(self.reading(ctx, mid, "abc", d(-10)).status_code, 422)
        repl = self.reading(ctx, mid, 10, d(-10), replaced=True)                             # счётчик заменили
        self.assertEqual((repl.status_code, float(repl.json()["consumption"])), (200, 0.0))
        good = self.reading(ctx, mid, 110, d(0))                                              # 100 кВт·ч × 6,5
        self.assertEqual(float(good.json()["cost"]), 650.0)
        first_id = self.client.get(f"/api/meters/{mid}/readings", headers=ctx["h"]).json()["readings"][-1]["id"]
        self.assertEqual(self.client.delete(f"/api/meter-readings/{first_id}", headers=ctx["h"]).status_code, 422)   # не последнее
        self.assertEqual(self.client.delete(f"/api/meter-readings/{good.json()['id']}", headers=ctx["h"]).status_code, 200)
        self.assertEqual(self.expenses(ctx), [])                                                           # расход удалился вместе с показанием
        self.assertEqual(len(self.client.get(f"/api/meters/{mid}/readings", headers=ctx["h"]).json()["readings"]), 2)

    def test_common_meter_roles_and_isolation(self):
        ctx = self.register("mt3@example.ru")
        other = self.register("mt3b@example.ru")
        maid = self.staff(ctx, "maid-mt3@example.ru")
        mid = self.meter(ctx, room_id=None, kind="heat", tariff=2000)
        m = self.client.get("/api/meters", headers=ctx["h"]).json()["meters"][0]
        self.assertIsNone(m["room_id"])
        self.assertEqual(self.client.get("/api/meters", headers=maid["h"]).status_code, 403)
        self.assertEqual(self.client.post(f"/api/meters/{mid}/readings", headers=maid["h"], json={"value": 1}).status_code, 403)
        self.assertEqual(self.reading(other, mid, 10).status_code, 404)
        self.assertEqual(self.client.get("/api/meters", headers=other["h"]).json()["meters"], [])
        self.assertEqual(self.client.post("/api/meters", headers=ctx["h"], json={"kind": "plasma"}).status_code, 422)
        self.assertEqual(self.client.post("/api/meters", headers=ctx["h"], json={"kind": "gas", "room_id": other["rooms"][0]["id"]}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/meters/{mid}", headers=other["h"], json={"tariff": 1}).status_code, 404)
        # архив убирает счётчик из списка
        self.client.patch(f"/api/meters/{mid}", headers=ctx["h"], json={"archived": True})
        self.assertEqual(self.client.get("/api/meters", headers=ctx["h"]).json()["meters"], [])


class InventoryTests(Mixin, Base):
    def add(self, ctx, room, name, qty=1):
        r = self.client.post(f"/api/rooms/{room['id']}/inventory", headers=ctx["h"], json={"name": name, "qty": qty})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_checklist_after_checkout_creates_tasks_and_alert_without_duplicates(self):
        ctx = self.register("inv1@example.ru")
        maid = self.staff(ctx, "maid-inv1@example.ru")
        room = ctx["rooms"][0]
        kettle, hair, towels = self.add(ctx, room, "Чайник"), self.add(ctx, room, "Фен"), self.add(ctx, room, "Полотенца", 4)
        inv = self.client.get(f"/api/rooms/{room['id']}/inventory", headers=maid["h"]).json()       # горничная видит список
        self.assertEqual([i["name"] for i in inv["items"]], ["Чайник", "Фен", "Полотенца"])
        self.assertIsNone(inv["last_check"])
        b = self.book(ctx, room, d(-3), d(0)).json()
        body = {"booking_id": b["id"], "items": [{"item_id": kettle["id"], "state": "ok"}, {"item_id": hair["id"], "state": "broken", "note": "не включается"},
                                                  {"item_id": towels["id"], "state": "missing"}, {"item_id": "00000000-0000-0000-0000-000000000000", "state": "missing"}]}
        r = self.client.post(f"/api/rooms/{room['id']}/inventory-check", headers=maid["h"], json=body)
        self.assertEqual((r.status_code, r.json()["problems"]), (200, 2), r.text)
        tasks = {t["title"]: t for t in self.client.get("/api/tasks", headers=ctx["h"]).json()["items"]}
        self.assertEqual(set(tasks), {"Номер 101: сломано — Фен", "Номер 101: не хватает — Полотенца"})
        self.assertEqual((tasks["Номер 101: сломано — Фен"]["source"], tasks["Номер 101: сломано — Фен"]["description"], tasks["Номер 101: сломано — Фен"]["booking_id"]), ("inventory", "не включается", b["id"]))
        notes = [n["text"] for n in self.client.get("/api/notifications", headers=ctx["h"]).json()["items"]]
        self.assertTrue(any("Номер 101" in t and "Фен (сломано)" in t and "Полотенца (нет)" in t for t in notes))
        # повторная проверка с теми же проблемами не плодит задачи
        self.client.post(f"/api/rooms/{room['id']}/inventory-check", headers=maid["h"], json=body)
        self.assertEqual(len(self.client.get("/api/tasks", headers=ctx["h"]).json()["items"]), 2)
        last = self.client.get(f"/api/rooms/{room['id']}/inventory", headers=maid["h"]).json()["last_check"]
        self.assertEqual((last["problems"], last["user_name"]), (2, "Мария"))
        hist = self.client.get(f"/api/rooms/{room['id']}/inventory-checks", headers=ctx["h"]).json()["checks"]
        self.assertEqual(len(hist), 2)
        self.assertEqual({i["name"] for i in hist[0]["items"]}, {"Фен", "Полотенца"})
        # полная проверка без проблем задач не создаёт
        ok = self.client.post(f"/api/rooms/{room['id']}/inventory-check", headers=maid["h"], json={"items": [{"item_id": kettle["id"], "state": "ok"}]})
        self.assertEqual(ok.json()["problems"], 0)

    def test_edit_copy_and_permissions(self):
        ctx = self.register("inv2@example.ru")
        other = self.register("inv2b@example.ru")
        maid = self.staff(ctx, "maid-inv2@example.ru")
        r1, r2 = ctx["rooms"][0], ctx["rooms"][1]      # оба — «Стандарт»
        deluxe = ctx["rooms"][-1]
        a = self.add(ctx, r1, "Телевизор")
        self.add(ctx, r1, "Плед", 2)
        self.add(ctx, r2, "Плед", 2)                    # уже есть — не дублируется
        res = self.client.post(f"/api/rooms/{r1['id']}/inventory/copy", headers=ctx["h"], json={}).json()
        self.assertEqual((res["rooms"], res["added"]), (7, 13))     # в остальные 7 номеров «Стандарта»: 2 позиции × 7 минус «Плед», который уже был в одном
        names2 = [i["name"] for i in self.client.get(f"/api/rooms/{r2['id']}/inventory", headers=ctx["h"]).json()["items"]]
        self.assertEqual(sorted(names2), ["Плед", "Телевизор"])
        self.assertEqual(self.client.get(f"/api/rooms/{deluxe['id']}/inventory", headers=ctx["h"]).json()["items"], [])   # другая категория не затронута
        self.assertEqual(self.client.patch(f"/api/inventory/{a['id']}", headers=ctx["h"], json={"qty": 0}).status_code, 422)   # количество не меньше 1
        r = self.client.patch(f"/api/inventory/{a['id']}", headers=ctx["h"], json={"name": "Смарт-ТВ", "qty": 2})
        self.assertEqual((r.json()["name"], r.json()["qty"]), ("Смарт-ТВ", 2))
        # горничная ничего не меняет; чужой аккаунт ничего не видит и не меняет
        self.assertEqual(self.client.post(f"/api/rooms/{r1['id']}/inventory", headers=maid["h"], json={"name": "X"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/inventory/{a['id']}", headers=maid["h"]).status_code, 403)
        self.assertEqual(self.client.get(f"/api/rooms/{r1['id']}/inventory", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/inventory/{a['id']}", headers=other["h"], json={"name": "Взлом"}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/rooms/{r1['id']}/inventory-check", headers=other["h"], json={"items": [{"item_id": a["id"], "state": "ok"}]}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/rooms/{r1['id']}/inventory-check", headers=ctx["h"], json={"items": []}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/rooms/{r1['id']}/inventory", headers=ctx["h"], json={"name": ""}).status_code, 422)
        self.assertEqual(self.client.delete(f"/api/inventory/{a['id']}", headers=ctx["h"]).status_code, 200)


if __name__ == "__main__":
    unittest.main()
