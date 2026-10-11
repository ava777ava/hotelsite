"""Раунд 5, этап 1: автопилот — задачи команды, код двери, анкета гостя, отзывы, сценарии «событие → действие»."""
import unittest

from test_app import Base, d  # noqa: F401  (test_app задаёт окружение для тестовой базы)

from app import db, notify, telegram


class StaffMixin:
    def staff(self, ctx, email, role="housekeeper", name="Мария"):
        r = self.client.post("/api/users", headers=ctx["h"], json={"name": name, "email": email, "role": role, "password": "password123"})
        self.assertEqual(r.status_code, 200, r.text)
        tok = self.client.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]
        return {"id": r.json()["id"], "h": {"Authorization": f"Bearer {tok}"}}


class TaskTests(StaffMixin, Base):
    def test_create_assign_and_mark_done_from_phone(self):
        ctx = self.register("tasks1@example.ru")
        maid = self.staff(ctx, "maid-t1@example.ru")
        r = self.client.post("/api/tasks", headers=ctx["h"], json={
            "title": "Заменить лампочку в 101", "assignee_id": maid["id"], "due_date": d(1), "room_id": ctx["rooms"][0]["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        t = r.json()
        self.assertEqual(t["assignee_name"], "Мария")
        self.assertEqual(t["room_name"], "101")
        self.assertFalse(t["overdue"])
        # горничная видит свою задачу и закрывает её
        mine = self.client.get("/api/tasks", headers=maid["h"]).json()
        self.assertEqual([x["id"] for x in mine["items"]], [t["id"]])
        self.assertEqual(mine["staff"], [])  # список сотрудников — только администратору
        r = self.client.post(f"/api/tasks/{t['id']}/done", headers=maid["h"], json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(r.json()["done_at"])
        self.assertEqual(r.json()["done_by_name"], "Мария")
        self.assertEqual(self.client.get("/api/tasks", headers=ctx["h"]).json()["items"], [])
        done = self.client.get("/api/tasks?scope=done", headers=ctx["h"]).json()["items"]
        self.assertEqual(len(done), 1)
        # можно вернуть в работу
        r = self.client.post(f"/api/tasks/{t['id']}/done", headers=maid["h"], json={"undo": True})
        self.assertIsNone(r.json()["done_at"])

    def test_housekeeper_cannot_touch_foreign_task_or_create(self):
        ctx = self.register("tasks2@example.ru")
        maid1 = self.staff(ctx, "m1-t2@example.ru", name="Анна")
        maid2 = self.staff(ctx, "m2-t2@example.ru", name="Вера")
        t = self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Принять бельё", "assignee_id": maid1["id"]}).json()
        r = self.client.post(f"/api/tasks/{t['id']}/done", headers=maid2["h"], json={})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get("/api/tasks", headers=maid2["h"]).json()["items"], [])  # чужую даже не видит
        self.assertEqual(self.client.post("/api/tasks", headers=maid2["h"], json={"title": "X"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/tasks/{t['id']}", headers=maid1["h"]).status_code, 403)
        # «общая» задача (без исполнителя) доступна всем горничным
        common = self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Протереть окна"}).json()
        self.assertEqual(len(self.client.get("/api/tasks", headers=maid2["h"]).json()["items"]), 1)
        self.assertEqual(self.client.post(f"/api/tasks/{common['id']}/done", headers=maid2["h"], json={}).status_code, 200)

    def test_overdue_flag_counts_and_badge(self):
        ctx = self.register("tasks3@example.ru")
        maid = self.staff(ctx, "m-t3@example.ru")
        self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Старая", "due_date": d(-2), "assignee_id": maid["id"]})
        self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Сегодня", "due_date": d(0)})
        self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Потом", "due_date": d(5)})
        lst = self.client.get("/api/tasks", headers=ctx["h"]).json()
        self.assertEqual(lst["counts"], {"open": 3, "overdue": 1, "today": 1})
        self.assertEqual([t["title"] for t in lst["items"]], ["Старая", "Сегодня", "Потом"])
        self.assertTrue(lst["items"][0]["overdue"])
        over = self.client.get("/api/tasks?scope=overdue", headers=ctx["h"]).json()["items"]
        self.assertEqual([t["title"] for t in over], ["Старая"])
        self.assertEqual(self.client.get("/api/badges", headers=ctx["h"]).json()["tasks"], 1)
        self.assertEqual(self.client.get("/api/badges", headers=maid["h"]).json()["tasks"], 1)

    def test_recurring_task_spawns_next_occurrence(self):
        ctx = self.register("tasks4@example.ru")
        t = self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Проверить огнетушители", "due_date": d(0), "recurrence": "weekly"}).json()
        r = self.client.post(f"/api/tasks/{t['id']}/done", headers=ctx["h"], json={})
        self.assertEqual(r.status_code, 200)
        open_ = self.client.get("/api/tasks", headers=ctx["h"]).json()["items"]
        self.assertEqual(len(open_), 1)
        self.assertEqual(open_[0]["title"], "Проверить огнетушители")
        self.assertEqual(open_[0]["due_date"], d(7))
        self.assertEqual(open_[0]["recurrence"], "weekly")
        # ежемесячная: следующий срок — через месяц; просроченная не копится в прошлом
        m = self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Счётчики", "due_date": d(-70), "recurrence": "monthly"}).json()
        self.client.post(f"/api/tasks/{m['id']}/done", headers=ctx["h"], json={})
        nxt = [t for t in self.client.get("/api/tasks", headers=ctx["h"]).json()["items"] if t["title"] == "Счётчики"]
        self.assertEqual(len(nxt), 1)
        self.assertGreaterEqual(nxt[0]["due_date"], d(0))

    def test_validation_and_account_isolation(self):
        ctx = self.register("tasks5@example.ru")
        other = self.register("tasks5b@example.ru")
        self.assertEqual(self.client.post("/api/tasks", headers=ctx["h"], json={"title": ""}).status_code, 422)
        self.assertEqual(self.client.post("/api/tasks", headers=ctx["h"], json={"title": "x", "recurrence": "daily"}).status_code, 422)
        self.assertEqual(self.client.post("/api/tasks", headers=ctx["h"], json={"title": "x", "recurrence": "weekly"}).status_code, 422)  # нужен срок
        self.assertEqual(self.client.post("/api/tasks", headers=ctx["h"], json={"title": "x", "due_date": "завтра"}).status_code, 422)
        self.assertEqual(self.client.post("/api/tasks", headers=ctx["h"], json={"title": "x", "room_id": other["rooms"][0]["id"]}).status_code, 404)
        t = self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Моя"}).json()
        self.assertEqual(self.client.post(f"/api/tasks/{t['id']}/done", headers=other["h"], json={}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/tasks/{t['id']}", headers=other["h"], json={"title": "взлом"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/tasks/{t['id']}", headers=other["h"]).status_code, 404)
        r = self.client.patch(f"/api/tasks/{t['id']}", headers=ctx["h"], json={"title": "Новое имя", "due_date": d(3)})
        self.assertEqual((r.json()["title"], r.json()["due_date"]), ("Новое имя", d(3)))
        self.assertEqual(self.client.delete(f"/api/tasks/{t['id']}", headers=ctx["h"]).status_code, 200)


class DoorCodeTests(StaffMixin, Base):
    def test_door_code_in_booking_room_default_and_placeholder(self):
        ctx = self.register("door1@example.ru")
        room = ctx["rooms"][0]
        b = self.book(ctx, room, d(2), d(4), guest="Анна Петрова", door_code="4821#").json()
        self.assertEqual(b["door_code"], "4821#")
        # постоянный код номера — запасной вариант
        r = self.client.patch(f"/api/rooms/{room['id']}", headers=ctx["h"], json={"door_code": "0000"})
        self.assertEqual(r.json()["door_code"], "0000")
        b2 = self.book(ctx, room, d(6), d(8), guest="Борис").json()
        for bid, expected in ((b["id"], "4821#"), (b2["id"], "0000")):
            msg = self.client.post(f"/api/bookings/{bid}/message", headers=ctx["h"], json={"body": "Код: {код двери}, {имя}"}).json()
            self.assertIn(expected, msg["text"])
        # без кода нигде — понятная подсказка, а не пустая строка
        room2 = ctx["rooms"][1]
        b3 = self.book(ctx, room2, d(2), d(3)).json()
        msg = self.client.post(f"/api/bookings/{b3['id']}/message", headers=ctx["h"], json={"body": "{код двери}"}).json()
        self.assertIn("уточните", msg["text"])
        # правка и история изменений
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"door_code": "9999"})
        hist = self.client.get(f"/api/bookings/{b['id']}/log", headers=ctx["h"]).json()
        self.assertTrue(any("Код двери" in str(x) for x in hist))

    def test_door_code_hidden_from_housekeeper(self):
        ctx = self.register("door2@example.ru")
        maid = self.staff(ctx, "maid-d2@example.ru")
        self.book(ctx, ctx["rooms"][0], d(0), d(2), door_code="1234")
        board = self.client.get("/api/board", headers=maid["h"]).json()
        self.assertTrue(board["bookings"])
        self.assertTrue(all(b["door_code"] == "" for b in board["bookings"]))
        board = self.client.get("/api/board", headers=ctx["h"]).json()
        self.assertEqual(board["bookings"][0]["door_code"], "1234")


if __name__ == "__main__":
    unittest.main()
