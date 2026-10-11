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


class GuestFormTests(StaffMixin, Base):
    def link(self, ctx, bid, kind):
        r = self.client.post(f"/api/bookings/{bid}/link", headers=ctx["h"], json={"kind": kind})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["url"]

    def test_guest_fills_questionnaire_by_secret_link(self):
        ctx = self.register("form1@example.ru")
        b = self.book(ctx, ctx["rooms"][0], d(3), d(5), guest="Анна Петрова", guests_count=2).json()
        url = self.link(ctx, b["id"], "form")
        self.assertTrue(url.startswith("https://fligel.test/f/"))
        self.assertEqual(self.link(ctx, b["id"], "form"), url)  # ссылка не меняется
        token = url.rsplit("/", 1)[1]
        # страница отдаётся без входа и без индексации
        page = self.client.get(f"/f/{token}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("noindex", page.text)
        self.assertEqual(page.headers["referrer-policy"], "no-referrer")
        info = self.client.get(f"/api/public/form/{token}").json()
        self.assertEqual(info["guest"], "Анна")
        self.assertFalse(info["filled"])
        self.assertEqual(info["answers"]["guests_count"], 2)
        self.assertNotIn("phone", str(info["answers"]))
        r = self.client.post(f"/api/public/form/{token}", json={"arrival_time": "18:30", "guests_count": 3,
                                                                 "wishes": "Детская кроватка", "car_number": "а123вб  116"})
        self.assertEqual(r.status_code, 200, r.text)
        # ответы видны сотруднику в карточке брони, номер машины приведён к виду А123ВБ 116
        form = self.client.get(f"/api/bookings/{b['id']}/form", headers=ctx["h"]).json()["form"]
        self.assertEqual((form["arrival_time"], form["guests_count"], form["wishes"], form["car_number"]),
                         ("18:30", 3, "Детская кроватка", "А123ВБ 116"))
        self.assertIsNotNone(form["filled_at"])
        # владельцу пришло уведомление в колокольчик
        notes = self.client.get("/api/notifications", headers=ctx["h"]).json()
        self.assertTrue(any("заполнил анкету" in n["text"] for n in notes["items"]))
        # можно обновить ответы
        self.assertEqual(self.client.post(f"/api/public/form/{token}", json={"guests_count": 2}).status_code, 200)

    def test_form_link_rejects_garbage_cancelled_and_foreign_access(self):
        ctx = self.register("form2@example.ru")
        other = self.register("form2b@example.ru")
        self.assertEqual(self.client.get("/api/public/form/nonexistent-token").status_code, 404)
        b = self.book(ctx, ctx["rooms"][0], d(3), d(4)).json()
        token = self.link(ctx, b["id"], "form").rsplit("/", 1)[1]
        self.assertEqual(self.client.post(f"/api/public/form/{token}", json={"guests_count": 0}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/public/form/{token}", json={"guests_count": 99}).status_code, 422)
        # чужой аккаунт не может ни получить ссылку, ни посмотреть ответы
        self.assertEqual(self.client.post(f"/api/bookings/{b['id']}/link", headers=other["h"], json={"kind": "form"}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/bookings/{b['id']}/form", headers=other["h"]).status_code, 404)
        self.assertEqual(self.client.post(f"/api/bookings/{b['id']}/link", headers=ctx["h"], json={"kind": "passport"}).status_code, 422)
        # отменённая бронь — ссылка перестаёт работать
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"status": "cancelled"})
        self.assertEqual(self.client.get(f"/api/public/form/{token}").status_code, 404)

    def test_questionnaire_has_no_passport_fields(self):
        # 152-ФЗ: анкета не собирает паспортные данные — ни в схеме, ни в странице
        with db.tx() as conn:
            cols = {r["column_name"] for r in db.all_(conn, "SELECT column_name FROM information_schema.columns WHERE table_name = 'booking_forms'")}
        self.assertEqual(cols, {"booking_id", "account_id", "token", "arrival_time", "guests_count", "wishes", "car_number", "filled_at", "created_at"})
        ctx = self.register("form3@example.ru")
        b = self.book(ctx, ctx["rooms"][0], d(3), d(4)).json()
        token = self.link(ctx, b["id"], "form").rsplit("/", 1)[1]
        page = self.client.get(f"/f/{token}").text.lower()
        self.assertNotIn("серия", page)
        self.assertIn("паспортные данные не нужны", page)

    def test_placeholders_create_links_on_demand(self):
        ctx = self.register("form4@example.ru")
        b = self.book(ctx, ctx["rooms"][0], d(3), d(4)).json()
        self.assertIsNone(self.client.get(f"/api/bookings/{b['id']}/form", headers=ctx["h"]).json()["form"])
        msg = self.client.post(f"/api/bookings/{b['id']}/message", headers=ctx["h"], json={"body": "Анкета: {ссылка на анкету}"}).json()["text"]
        self.assertIn("https://fligel.test/f/", msg)
        self.assertIsNotNone(self.client.get(f"/api/bookings/{b['id']}/form", headers=ctx["h"]).json()["form"])


class ReviewTests(StaffMixin, Base):
    def test_review_flow_stats_and_low_rating_alert(self):
        ctx = self.register("rev1@example.ru")
        tg = []
        telegram.send_message = lambda chat, text: tg.append((chat, text))
        r1, r2 = ctx["rooms"][0], ctx["rooms"][1]
        past = self.book(ctx, r1, d(-5), d(-3), guest="Иван Смирнов").json()
        past2 = self.book(ctx, r2, d(-6), d(-4), guest="Ольга Орлова").json()
        future = self.book(ctx, r1, d(10), d(12)).json()
        tok = lambda b: self.client.post(f"/api/bookings/{b['id']}/link", headers=ctx["h"], json={"kind": "review"}).json()["url"].rsplit("/", 1)[1]
        t1, t2, tf = tok(past), tok(past2), tok(future)
        self.assertEqual(self.client.get(f"/r/{t1}").status_code, 200)
        info = self.client.get(f"/api/public/review/{t1}").json()
        self.assertTrue(info["can_review"])
        self.assertEqual(info["guest"], "Иван")
        # до заезда отзыв оставить нельзя
        self.assertEqual(self.client.post(f"/api/public/review/{tf}", json={"rating": 5}).status_code, 422)
        # оценка 1–5
        for bad in (0, 6, "", None):
            self.assertEqual(self.client.post(f"/api/public/review/{t1}", json={"rating": bad}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/public/review/{t1}", json={"rating": 5, "comment": "Чисто и тихо"}).status_code, 200)
        before = len(self.client.get("/api/notifications", headers=ctx["h"]).json()["items"])
        self.assertEqual(self.client.post(f"/api/public/review/{t2}", json={"rating": 2, "comment": "Шумно"}).status_code, 200)
        items = self.client.get("/api/notifications", headers=ctx["h"]).json()["items"]
        self.assertEqual(len(items), before + 1)
        self.assertIn("Низкая оценка 2 из 5", items[0]["text"])
        # повторная низкая оценка того же гостя не шлёт второе уведомление
        self.client.post(f"/api/public/review/{t2}", json={"rating": 1, "comment": "Очень шумно"})
        self.assertEqual(len(self.client.get("/api/notifications", headers=ctx["h"]).json()["items"]), before + 1)
        st = self.client.get("/api/reviews", headers=ctx["h"]).json()
        self.assertEqual(st["overall"]["n"], 2)
        self.assertEqual(float(st["overall"]["avg"]), 3.0)  # (5 + 1) / 2
        self.assertEqual(st["overall"]["low"], 1)
        self.assertEqual({x["name"]: float(x["avg"]) for x in st["by_room"]}, {"101": 5.0, "102": 1.0})
        self.assertEqual(st["by_room"][0]["name"], "102")  # худшие сверху
        self.assertEqual(st["waiting"], 1)
        self.assertEqual(st["items"][0]["comment"], "Очень шумно")
        # у сотрудника в карточке брони виден отзыв
        rv = self.client.get(f"/api/bookings/{past['id']}/form", headers=ctx["h"]).json()["review"]
        self.assertEqual((rv["rating"], rv["comment"]), (5, "Чисто и тихо"))

    def test_review_stats_are_per_account_and_manager_only(self):
        ctx = self.register("rev2@example.ru")
        other = self.register("rev2b@example.ru")
        maid = self.staff(ctx, "maid-rev2@example.ru")
        b = self.book(ctx, ctx["rooms"][0], d(-4), d(-2)).json()
        tok = self.client.post(f"/api/bookings/{b['id']}/link", headers=ctx["h"], json={"kind": "review"}).json()["url"].rsplit("/", 1)[1]
        self.client.post(f"/api/public/review/{tok}", json={"rating": 4})
        self.assertEqual(self.client.get("/api/reviews", headers=other["h"]).json()["overall"]["n"], 0)
        self.assertEqual(self.client.get("/api/reviews", headers=maid["h"]).status_code, 403)
        self.assertEqual(self.client.get("/api/reviews", headers=ctx["h"]).json()["overall"]["n"], 1)
        self.assertEqual(self.client.get("/api/public/review/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
