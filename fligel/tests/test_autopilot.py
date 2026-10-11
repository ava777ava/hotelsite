"""Раунд 5, этап 1: автопилот — задачи команды, код двери, анкета гостя, отзывы, сценарии «событие → действие»."""
import unittest

from test_app import Base, d  # noqa: F401  (test_app задаёт окружение для тестовой базы)

from app import automation, config, db, mail, notify, telegram


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


class AutopilotTests(StaffMixin, Base):
    def setUp(self):
        self.sent = []
        self._mail = (mail.send, config.SMTP_HOST)
        mail.send = lambda to, subject, body: self.sent.append((to, subject, body))
        config.SMTP_HOST = "smtp.test"  # почта «настроена»: письма уходят в наш мок

    def tearDown(self):
        mail.send, config.SMTP_HOST = self._mail

    def rules(self, ctx):
        r = self.client.get("/api/automation", headers=ctx["h"])
        self.assertEqual(r.status_code, 200, r.text)
        return {x["preset"] or x["name"]: x for x in r.json()["rules"]}

    def soon(self, ctx, key, **patch):
        """Проверяем одно правило: остальные выключаем, а у него час срабатывания 0 — тест не зависит от времени суток."""
        rules = self.rules(ctx)
        for k, v in rules.items():
            if k != key and v["enabled"]:
                self.client.patch(f"/api/automation/rules/{v['id']}", headers=ctx["h"], json={"enabled": False})
        r = self.client.patch(f"/api/automation/rules/{rules[key]['id']}", headers=ctx["h"], json={"at_hour": 0, "enabled": True, **patch})
        self.assertEqual(r.status_code, 200, r.text)
        return rules[key]

    def runs(self, ctx):
        return self.client.get("/api/automation/runs", headers=ctx["h"]).json()["items"]

    def test_presets_created_for_new_account_with_safe_defaults(self):
        ctx = self.register("auto1@example.ru")
        rules = self.rules(ctx)
        self.assertEqual(set(rules), {p["key"] for p in automation.PRESETS})
        on = {k for k, v in rules.items() if v["enabled"]}
        self.assertEqual(on, {"checkin_instructions", "payment_reminder", "cleaning_after_checkout", "debt_alert"})
        self.assertTrue(all(v["hint"] for v in rules.values()))
        # старый аккаунт (сценариев ещё нет) получает их выключенными — ничего не уйдёт гостям без ведома владельца
        with db.tx() as conn:
            db.run(conn, "DELETE FROM automation_rules WHERE account_id = (SELECT account_id FROM users WHERE email = 'auto1@example.ru')")
        rules = self.rules(ctx)
        self.assertEqual(len(rules), len(automation.PRESETS))
        self.assertFalse(any(v["enabled"] for v in rules.values()))

    def test_checkin_instructions_email_once_with_door_code(self):
        ctx = self.register("auto2@example.ru")
        self.soon(ctx, "checkin_instructions")
        b = self.book(ctx, ctx["rooms"][0], d(1), d(3), guest="Анна Петрова", guest_email="anna@guest.ru", door_code="4821#").json()
        self.book(ctx, ctx["rooms"][1], d(1), d(3), guest="Без почты")  # другой гость без email
        automation.run_due()
        mine = [m for m in self.sent if m[0] == "anna@guest.ru"]
        self.assertEqual(len(mine), 1)
        self.assertIn("4821#", mine[0][2])
        self.assertIn("Анна", mine[0][2])
        self.assertNotIn("{", mine[0][1] + mine[0][2])  # все подстановки заменены
        runs = [r for r in self.runs(ctx) if r["booking_id"] == b["id"]]
        self.assertEqual([r["status"] for r in runs], ["done"])
        # повторный проход не шлёт письмо второй раз
        automation.run_due()
        self.assertEqual(len([m for m in self.sent if m[0] == "anna@guest.ru"]), 1)
        # гостю без email — не письмо, а напоминание сотрудникам
        skipped = [r for r in self.runs(ctx) if r["guest_name"] == "Без почты"]
        self.assertEqual(skipped[0]["status"], "skipped")
        notes = self.client.get("/api/notifications", headers=ctx["h"]).json()["items"]
        self.assertTrue(any("не указан email" in n["text"] and "Без почты" in n["text"] for n in notes))

    def test_email_skipped_when_smtp_not_configured(self):
        ctx = self.register("auto3@example.ru")
        self.soon(ctx, "checkin_instructions")
        config.SMTP_HOST = ""
        self.book(ctx, ctx["rooms"][0], d(1), d(2), guest_email="g@guest.ru")
        automation.run_due()
        self.assertEqual(self.sent, [])
        self.assertIn("SMTP", self.runs(ctx)[0]["detail"])
        self.assertEqual(self.runs(ctx)[0]["status"], "skipped")

    def test_payment_reminder_only_for_unpaid_and_catches_up(self):
        ctx = self.register("auto4@example.ru")
        self.soon(ctx, "payment_reminder")
        self.book(ctx, ctx["rooms"][0], d(2), d(4), guest="Должник", guest_email="debtor@guest.ru")        # до заезда 2 дня: окно «за 3 дня» уже открыто
        self.book(ctx, ctx["rooms"][1], d(2), d(4), guest="Заплатил", guest_email="paid@guest.ru", paid_amount=7000)
        self.book(ctx, ctx["rooms"][2], d(10), d(12), guest="Далеко", guest_email="far@guest.ru")          # рано
        automation.run_due()
        self.assertEqual([m[0] for m in self.sent], ["debtor@guest.ru"])
        self.assertIn("осталось внести", self.sent[0][2])

    def test_cancelled_booking_does_not_trigger(self):
        ctx = self.register("auto5@example.ru")
        self.soon(ctx, "checkin_instructions")
        b = self.book(ctx, ctx["rooms"][0], d(1), d(2), guest_email="x@guest.ru").json()
        self.client.patch(f"/api/bookings/{b['id']}", headers=ctx["h"], json={"status": "cancelled"})
        automation.run_due()
        self.assertEqual(self.sent, [])

    def test_cleaning_after_checkout_sets_status_unless_already_cleaned(self):
        ctx = self.register("auto6@example.ru")
        self.soon(ctx, "cleaning_after_checkout")
        r1, r2 = ctx["rooms"][0], ctx["rooms"][1]
        self.book(ctx, r1, d(-2), d(0), guest="Уехал")
        self.book(ctx, r2, d(-2), d(0), guest="Уехал рано")
        with db.tx() as conn:  # горничная уже убрала второй номер сегодня утром
            db.run(conn, "UPDATE rooms SET cleaned_on = current_date WHERE id = %s", (r2["id"],))
        automation.run_due()
        with db.tx() as conn:
            st = {str(r["id"]): r["hk_status"] for r in db.all_(conn, "SELECT id, hk_status FROM rooms WHERE id = ANY(%s::uuid[])", ([r1["id"], r2["id"]],))}
            logged = db.one(conn, "SELECT count(*) AS n FROM room_status_log WHERE room_id = %s AND user_id IS NULL", (r1["id"],))["n"]
        self.assertEqual(st[str(r1["id"])], "dirty")
        self.assertEqual(st[str(r2["id"])], "clean")
        self.assertEqual(logged, 1)
        details = {r["guest_name"]: r["status"] for r in self.runs(ctx)}
        self.assertEqual(details, {"Уехал": "done", "Уехал рано": "skipped"})

    def test_debt_alert_goes_to_staff_bell(self):
        ctx = self.register("auto7@example.ru")
        self.soon(ctx, "debt_alert")
        self.book(ctx, ctx["rooms"][0], d(-3), d(0), guest="Иван Должников", guest_phone="+79001112233", paid_amount=1000)
        self.book(ctx, ctx["rooms"][1], d(-3), d(0), guest="Рассчитался", paid_amount=10500)
        automation.run_due()
        notes = [n["text"] for n in self.client.get("/api/notifications", headers=ctx["h"]).json()["items"]]
        self.assertEqual(len([t for t in notes if "не оплачено" in t]), 1)
        msg = [t for t in notes if "не оплачено" in t][0]
        self.assertIn("Иван Должников", msg)
        self.assertIn("9 500 ₽", msg)

    def test_custom_rule_creates_task_and_new_booking_is_not_retroactive(self):
        ctx = self.register("auto8@example.ru")
        maid = self.staff(ctx, "maid-a8@example.ru")
        old = self.book(ctx, ctx["rooms"][0], d(5), d(6), guest="Старая бронь").json()
        r = self.client.post("/api/automation/rules", headers=ctx["h"], json={
            "name": "Приготовить детскую кроватку", "event": "new_booking", "action": "create_task", "sources": ["manual"],
            "params": {"title": "Кроватка в номер {номер} для {гость}", "assignee_id": maid["id"], "due_in_days": 1}})
        self.assertEqual(r.status_code, 200, r.text)
        self.book(ctx, ctx["rooms"][1], d(7), d(8), guest="Новая бронь", source="avito")   # другой источник — мимо условия
        new = self.book(ctx, ctx["rooms"][2], d(7), d(8), guest="Мария Новикова").json()
        automation.run_due()
        tasks = self.client.get("/api/tasks", headers=ctx["h"]).json()["items"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Кроватка в номер 103 для Мария Новикова")
        self.assertEqual((tasks[0]["assignee_name"], tasks[0]["source"], tasks[0]["booking_id"]), ("Мария", "automation", new["id"]))
        self.assertEqual(tasks[0]["due_date"], d(1))
        self.assertNotIn(old["id"], [t["booking_id"] for t in tasks])

    def test_hour_condition_delays_firing(self):
        from datetime import datetime
        if datetime.now().hour >= 23:
            self.skipTest("нужен час позже текущего")
        ctx = self.register("auto9@example.ru")
        rule = self.soon(ctx, "checkin_instructions", at_hour=datetime.now().hour + 1)
        self.book(ctx, ctx["rooms"][0], d(1), d(2), guest_email="late@guest.ru")
        automation.run_due()
        self.assertEqual(self.sent, [])
        self.client.patch(f"/api/automation/rules/{rule['id']}", headers=ctx["h"], json={"at_hour": 0})
        automation.run_due()
        self.assertEqual(len(self.sent), 1)

    def test_disabled_rule_does_nothing_and_enable_toggle_is_audited(self):
        ctx = self.register("auto10@example.ru")
        rule = self.soon(ctx, "checkin_instructions")
        r = self.client.patch(f"/api/automation/rules/{rule['id']}", headers=ctx["h"], json={"enabled": False})
        self.assertFalse(r.json()["enabled"])
        self.book(ctx, ctx["rooms"][0], d(1), d(2), guest_email="off@guest.ru")
        automation.run_due()
        self.assertEqual(self.sent, [])
        log = self.client.get("/api/audit", headers=ctx["h"]).json()
        self.assertTrue(any("выключен" in str(x) for x in (log.get("items") if isinstance(log, dict) else log)))

    def test_rule_validation_permissions_and_isolation(self):
        ctx = self.register("auto11@example.ru")
        other = self.register("auto11b@example.ru")
        manager = self.staff(ctx, "mgr-a11@example.ru", role="manager", name="Админ")
        good = {"name": "Свой", "event": "checkout_day", "action": "notify_staff", "params": {"text": "Выезд {гость}"}}
        self.assertEqual(self.client.get("/api/automation", headers=manager["h"]).status_code, 403)
        self.assertEqual(self.client.post("/api/automation/rules", headers=manager["h"], json=good).status_code, 403)
        for patch in ({"event": "never"}, {"action": "format_disk"}, {"at_hour": 25}, {"offset_days": -1}, {"name": ""},
                      {"sources": ["tiktok"]}, {"params": {"text": ""}}, {"property_id": other["prop"]["id"]}):
            r = self.client.post("/api/automation/rules", headers=ctx["h"], json={**good, **patch})
            self.assertIn(r.status_code, (404, 422), (patch, r.text))
        r = self.client.post("/api/automation/rules", headers=ctx["h"], json=good)
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["id"]
        # чужой аккаунт не видит и не меняет
        self.assertNotIn(rid, [x["id"] for x in self.client.get("/api/automation", headers=other["h"]).json()["rules"]])
        self.assertEqual(self.client.patch(f"/api/automation/rules/{rid}", headers=other["h"], json={"enabled": False}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/automation/rules/{rid}", headers=other["h"]).status_code, 404)
        # готовый сценарий не удалить, свой — можно; у готового нельзя поменять событие
        preset = self.rules(ctx)["debt_alert"]
        self.assertEqual(self.client.delete(f"/api/automation/rules/{preset['id']}", headers=ctx["h"]).status_code, 422)
        r = self.client.patch(f"/api/automation/rules/{preset['id']}", headers=ctx["h"], json={"event": "new_booking", "action": "email_guest"})
        self.assertEqual((r.json()["event"], r.json()["action"]), ("debt", "notify_staff"))
        self.assertEqual(self.client.delete(f"/api/automation/rules/{rid}", headers=ctx["h"]).status_code, 200)

    def test_run_now_endpoint_and_overdue_task_reminder(self):
        ctx = self.register("auto12@example.ru")
        self.client.post("/api/tasks", headers=ctx["h"], json={"title": "Забытая задача", "due_date": d(-1)})
        old = automation.OVERDUE_HOUR
        automation.OVERDUE_HOUR = 0
        try:
            automation.run_due()
            automation.run_due()  # второй проход в тот же день — без повторного сообщения
        finally:
            automation.OVERDUE_HOUR = old
        notes = [n["text"] for n in self.client.get("/api/notifications", headers=ctx["h"]).json()["items"] if "Просрочено" in n["text"]]
        self.assertEqual(len(notes), 1)
        self.assertIn("Забытая задача", notes[0])
        self.assertEqual(self.client.post("/api/automation/run", headers=ctx["h"], json={}).json(), {"fired": 0})

    def test_messenger_events_include_automation(self):
        ctx = self.register("auto13@example.ru")
        st = self.client.get("/api/notify/status", headers=ctx["h"]).json()
        keys = {e["key"] for e in st["available_events"]}
        self.assertTrue({"automation", "task", "review"} <= keys)
        self.assertTrue({"automation", "task", "review"} <= set(st["events"]))


if __name__ == "__main__":
    unittest.main()
