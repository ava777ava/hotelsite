"""Демо-данные для знакомства с системой: python -m app.demo
Создаёт аккаунт demo@fligel.ru / demo12345 с гостиницей на 12 номеров и бронями."""
import random
from datetime import date, timedelta

from .auth import hash_password, new_ical_token
from .db import one, run, tx
from .migrate import migrate

GUESTS = ["Анна Ковалёва", "Игорь Петров", "Семья Смирновых", "Ольга Белова", "Дмитрий Орлов", "Марина Фролова",
          "Алексей Никитин", "Татьяна Гусева", "Сергей Волков", "Екатерина Зайцева", "Павел Сорокин", "Наталья Егорова",
          "Роман Лебедев", "Ирина Козлова", "Виктор Морозов"]


def main() -> None:
    migrate()
    rnd = random.Random(7)
    today = date.today()
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
        for rid, price in rooms:
            d = today - timedelta(days=rnd.randint(0, 6))
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
                    (acc, prop, rid, d, d + timedelta(days=nights), status, src, guest,
                     f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
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
            d = today - timedelta(days=rnd.randint(0, 6))
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
                    (acc, prop2, rid, d, d + timedelta(days=nights), status, src, guest,
                     f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
                     rnd.choice([1, 2]), total, total if status == "confirmed" and rnd.random() < 0.6 else 0))
                d += timedelta(days=nights)
    print("Готово: войдите как demo@fligel.ru / demo12345, страница бронирования — /book/demo")


if __name__ == "__main__":
    main()
