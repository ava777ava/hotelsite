"""Демо-данные для знакомства с системой: python -m app.demo
Создаёт аккаунт demo@fligel.ru / demo12345 с гостиницей на 12 номеров и бронями."""
import random
from datetime import date, timedelta

from .auth import hash_password, new_ical_token
from .db import all_, one, run, tx
from .expenses import create_default_categories
from .migrate import migrate

GUESTS = ["Анна Ковалёва", "Игорь Петров", "Семья Смирновых", "Ольга Белова", "Дмитрий Орлов", "Марина Фролова",
          "Алексей Никитин", "Татьяна Гусева", "Сергей Волков", "Екатерина Зайцева", "Павел Сорокин", "Наталья Егорова",
          "Роман Лебедев", "Ирина Козлова", "Виктор Морозов"]


def main() -> None:
    migrate()
    rnd = random.Random(7)
    today = date.today()
    # один и тот же гость всегда с одним и тем же телефоном — иначе в «Истории гостя»
    # никогда не наберётся больше одного визита и «постоянных гостей» не появится
    guest_phones = {
        name: f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}"
        for name in GUESTS
    }
    with tx() as conn:
        if one(conn, "SELECT 1 FROM users WHERE email = 'demo@fligel.ru'"):
            print("Демо-аккаунт уже есть: demo@fligel.ru / demo12345")
            return
        acc = one(conn, "INSERT INTO accounts (name) VALUES ('Гостиница «Флигель»') RETURNING id")["id"]
        run(conn, "INSERT INTO users (account_id, email, password_hash, name, role) VALUES (%s, %s, %s, %s, 'owner')",
            (acc, "demo@fligel.ru", hash_password("demo12345"), "Андрей"))
        prop = one(conn, "INSERT INTO properties (account_id, name, address, phone, public_slug) VALUES"
                         " (%s, 'Гостиница «Флигель»', 'Казань, ул. Пушкина, 12', '+7 900 000-00-00', 'demo') RETURNING id",
                   (acc,))["id"]
        rooms = []
        for i, (name, count, price, cap, desc) in enumerate([
            ("Стандарт", 8, 3500, 2, "Двуспальная кровать, душ, рабочий стол"),
            ("Делюкс", 4, 5500, 3, "Большой номер с диваном и видом во двор"),
        ]):
            rt = one(conn, "INSERT INTO room_types (account_id, property_id, name, description, capacity, base_price,"
                           " sort_order, ical_token) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                     (acc, prop, name, desc, cap, price, i, new_ical_token()))["id"]
            for _ in range(count):
                no = 101 + len(rooms)
                rid = one(conn, "INSERT INTO rooms (account_id, property_id, room_type_id, name, sort_order, ical_token)"
                                " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                          (acc, prop, rt, str(no), no, new_ical_token()))["id"]
                rooms.append((rid, price))
            # выходные дороже
            d = today
            while d < today + timedelta(days=60):
                if d.weekday() in (4, 5):
                    run(conn, "INSERT INTO rates (account_id, room_type_id, date, price) VALUES (%s, %s, %s, %s)",
                        (acc, rt, d, price + 1000))
                d += timedelta(days=1)
        sources = ["avito", "avito", "yandex", "yandex", "direct", "manual", "sutochno"]
        history_days = 390  # чуть больше года — чтобы отчёты показывали 12 полных месяцев и сравнение с прошлым годом
        for rid, price in rooms:
            d = today - timedelta(days=history_days - rnd.randint(0, 6))
            while d < today + timedelta(days=40):
                d += timedelta(days=rnd.randint(0, 3))
                nights = rnd.choice([1, 2, 2, 3, 3, 4, 5, 7])
                src = rnd.choice(sources)
                status = "pending" if src == "direct" and rnd.random() < 0.5 else "confirmed"
                guest = rnd.choice(GUESTS)
                total = price * nights
                run(conn, "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, source,"
                          " guest_name, guest_phone, guests_count, total_price, paid_amount)"
                          " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (acc, prop, rid, d, d + timedelta(days=nights), status, src, guest, guest_phones[guest],
                     rnd.choice([1, 2, 2]), total, total if status == "confirmed" and rnd.random() < 0.6 else 0))
                d += timedelta(days=nights)
        # ремонт в одном номере
        run(conn, "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, notes)"
                  " VALUES (%s, %s, %s, %s, %s, 'blocked', 'Ремонт') ON CONFLICT DO NOTHING",
            (acc, prop, rooms[-1][0], today + timedelta(days=45), today + timedelta(days=50)))

        # второй объект того же владельца: квартиры посуточно
        prop2 = one(conn, "INSERT INTO properties (account_id, name, address, phone, public_slug) VALUES"
                          " (%s, 'Квартиры на сутки', 'Казань, ул. Баумана, 5', '+7 900 111-22-33', 'apartments')"
                          " RETURNING id", (acc,))["id"]
        rt2 = one(conn, "INSERT INTO room_types (account_id, property_id, name, description, capacity, base_price,"
                        " sort_order, ical_token) VALUES (%s, %s, 'Квартира', 'Студия с кухней в центре города',"
                        " %s, %s, 0, %s) RETURNING id", (acc, prop2, 3, 2800, new_ical_token()))["id"]
        rooms2 = []
        for i in range(3):
            no = i + 1
            rid = one(conn, "INSERT INTO rooms (account_id, property_id, room_type_id, name, sort_order, ical_token)"
                            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                      (acc, prop2, rt2, f"Кв. {no}", no, new_ical_token()))["id"]
            rooms2.append((rid, 2800))
        for rid, price in rooms2:
            d = today - timedelta(days=history_days - rnd.randint(0, 6))
            while d < today + timedelta(days=40):
                d += timedelta(days=rnd.randint(0, 3))
                nights = rnd.choice([1, 2, 2, 3, 4])
                src = rnd.choice(sources)
                status = "pending" if src == "direct" and rnd.random() < 0.5 else "confirmed"
                guest = rnd.choice(GUESTS)
                total = price * nights
                run(conn, "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, source,"
                          " guest_name, guest_phone, guests_count, total_price, paid_amount)"
                          " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (acc, prop2, rid, d, d + timedelta(days=nights), status, src, guest, guest_phones[guest],
                     rnd.choice([1, 2]), total, total if status == "confirmed" and rnd.random() < 0.6 else 0))
                d += timedelta(days=nights)

        # расходы за последние 12 месяцев по разным категориям
        create_default_categories(conn, acc)
        cats = {c["name"]: c["id"] for c in all_(conn, "SELECT id, name FROM expense_categories WHERE account_id = %s",
                                                 (acc,))}
        month_start = today.replace(day=1)
        for i in range(12):
            m = month_start
            for _ in range(i):
                m = (m - timedelta(days=1)).replace(day=1)
            for prop_id, base_cleaning, base_utilities in ((prop, 9000, 14000), (prop2, 4000, 6000)):
                run(conn, "INSERT INTO expenses (account_id, property_id, category_id, date, amount, comment)"
                          " VALUES (%s, %s, %s, %s, %s, %s)",
                    (acc, prop_id, cats["Уборка и прачечная"], m + timedelta(days=rnd.randint(1, 5)),
                     base_cleaning + rnd.randint(-1000, 2000), "Клининг номеров"))
                run(conn, "INSERT INTO expenses (account_id, property_id, category_id, date, amount, comment)"
                          " VALUES (%s, %s, %s, %s, %s, %s)",
                    (acc, prop_id, cats["Коммунальные услуги"], m + timedelta(days=rnd.randint(5, 10)),
                     base_utilities + rnd.randint(-2000, 3000), "Свет, вода, отопление"))
                run(conn, "INSERT INTO expenses (account_id, property_id, category_id, date, amount, comment)"
                          " VALUES (%s, %s, %s, %s, %s, %s)",
                    (acc, prop_id, cats["Комиссии площадок"], m + timedelta(days=rnd.randint(10, 20)),
                     rnd.randint(3000, 9000), "Комиссия Авито/Яндекс за месяц"))
                if rnd.random() < 0.4:
                    run(conn, "INSERT INTO expenses (account_id, property_id, category_id, date, amount, comment)"
                              " VALUES (%s, %s, %s, %s, %s, %s)",
                        (acc, prop_id, cats["Ремонт и обслуживание"], m + timedelta(days=rnd.randint(1, 25)),
                         rnd.randint(2000, 15000), "Мелкий ремонт"))
            # общие расходы аккаунта, без привязки к объекту
            run(conn, "INSERT INTO expenses (account_id, property_id, category_id, date, amount, comment)"
                      " VALUES (%s, NULL, %s, %s, %s, %s)",
                (acc, cats["Зарплата"], m + timedelta(days=3), 65000, "Зарплата администратора"))
            run(conn, "INSERT INTO expenses (account_id, property_id, category_id, date, amount, comment)"
                      " VALUES (%s, NULL, %s, %s, %s, %s)",
                (acc, cats["Аренда/ипотека"], m + timedelta(days=1), 45000, "Аренда офиса"))
            if rnd.random() < 0.5:
                run(conn, "INSERT INTO expenses (account_id, property_id, category_id, date, amount, comment)"
                          " VALUES (%s, NULL, %s, %s, %s, %s)",
                    (acc, cats["Реклама"], m + timedelta(days=rnd.randint(1, 28)), rnd.randint(3000, 12000),
                     "Продвижение объявлений"))
        # шаблон повторяющегося расхода — аренда 1-го числа каждого месяца
        run(conn, "INSERT INTO expense_recurring_rules (account_id, category_id, amount, day_of_month, comment)"
                  " VALUES (%s, %s, %s, %s, %s)",
            (acc, cats["Аренда/ипотека"], 45000, 1, "Аренда офиса (автоматически)"))
        # комиссии площадок — для отчёта «чистая выручка по источникам»
        for channel, percent in (("avito", 12), ("yandex", 15), ("sutochno", 10)):
            run(conn, "INSERT INTO channel_commissions (account_id, channel, percent) VALUES (%s, %s, %s)",
                (acc, channel, percent))
    print("Готово: войдите как demo@fligel.ru / demo12345, страница бронирования — /book/demo")


if __name__ == "__main__":
    main()
