"""Нагрузочные демо-данные: 70 номеров, 2 года броней и расходов.

Отдельный аккаунт (не трогает обычные демо-данные из app/demo.py) — нужен, чтобы проверить,
что шахматка, отчёты и списки броней открываются быстро на реалистично большом объёме данных.

Запуск: python -m app.demo_load
"""
import random
import time
from datetime import date, timedelta

from .auth import hash_password, new_ical_token
from .db import all_, one, run, tx
from .expenses import create_default_categories
from .migrate import migrate

EMAIL = "loadtest@fligel.ru"
PASSWORD = "loadtest12345"
HISTORY_DAYS = 730  # 2 года


def main() -> None:
    migrate()
    rnd = random.Random(42)
    today = date.today()
    t0 = time.monotonic()
    with tx() as conn:
        if one(conn, "SELECT 1 FROM users WHERE email = %s", (EMAIL,)):
            print(f"Нагрузочный аккаунт уже есть: {EMAIL} / {PASSWORD}")
            return
        acc = one(conn, "INSERT INTO accounts (name) VALUES ('Нагрузочный тест: Большой отель') RETURNING id")["id"]
        run(conn, "INSERT INTO users (account_id, email, password_hash, name, role) VALUES (%s, %s, %s, %s, 'owner')",
            (acc, EMAIL, hash_password(PASSWORD), "Нагрузочный владелец"))
        prop = one(conn, "INSERT INTO properties (account_id, name, address, phone, public_slug) VALUES"
                         " (%s, 'Большой отель', 'Москва, Тестовая ул., 1', '+7 900 000-11-22', 'loadtest')"
                         " RETURNING id", (acc,))["id"]

        rooms: list[tuple[str, int]] = []
        categories = [("Стандарт", 30, 3000, 2), ("Комфорт", 20, 4200, 2), ("Делюкс", 12, 6000, 3),
                      ("Люкс", 6, 9500, 4), ("Апартаменты", 2, 15000, 6)]
        no = 100
        for i, (name, count, price, cap) in enumerate(categories):
            rt = one(conn, "INSERT INTO room_types (account_id, property_id, name, capacity, base_price,"
                           " sort_order, ical_token) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                     (acc, prop, name, cap, price, i, new_ical_token()))["id"]
            for _ in range(count):
                no += 1
                rid = one(conn, "INSERT INTO rooms (account_id, property_id, room_type_id, name, sort_order,"
                                " ical_token) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                          (acc, prop, rt, str(no), no, new_ical_token()))["id"]
                rooms.append((rid, price))
        assert len(rooms) == 70, len(rooms)

        sources = ["avito", "avito", "yandex", "yandex", "direct", "manual", "sutochno"]
        booking_count = 0
        for rid, price in rooms:
            d = today - timedelta(days=HISTORY_DAYS)
            while d < today + timedelta(days=40):
                d += timedelta(days=rnd.randint(0, 3))
                nights = rnd.choice([1, 2, 2, 3, 3, 4, 5, 7])
                src = rnd.choice(sources)
                status = "pending" if src == "direct" and rnd.random() < 0.5 else "confirmed"
                total = price * nights
                run(conn, "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status,"
                          " source, guest_name, guest_phone, guests_count, total_price, paid_amount)"
                          " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (acc, prop, rid, d, d + timedelta(days=nights), status, src, f"Гость {rnd.randint(1, 4000)}",
                     f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
                     rnd.choice([1, 2]), total, total if status == "confirmed" and rnd.random() < 0.6 else 0))
                booking_count += 1
                d += timedelta(days=nights)

        create_default_categories(conn, acc)
        cats = {c["name"]: c["id"] for c in all_(conn, "SELECT id, name FROM expense_categories WHERE account_id = %s",
                                                 (acc,))}
        month_start = today.replace(day=1)
        expense_count = 0
        for i in range(24):
            m = month_start
            for _ in range(i):
                m = (m - timedelta(days=1)).replace(day=1)
            for cat_name, lo, hi, prop_bound in (
                ("Уборка и прачечная", 60000, 100000, True), ("Коммунальные услуги", 90000, 160000, True),
                ("Комиссии площадок", 40000, 90000, True), ("Ремонт и обслуживание", 5000, 40000, True),
                ("Зарплата", 380000, 420000, False), ("Аренда/ипотека", 250000, 250000, False),
            ):
                run(conn, "INSERT INTO expenses (account_id, property_id, category_id, date, amount, comment)"
                          " VALUES (%s, %s, %s, %s, %s, %s)",
                    (acc, prop if prop_bound else None, cats[cat_name], m + timedelta(days=rnd.randint(1, 20)),
                     rnd.randint(lo, hi), cat_name))
                expense_count += 1
    elapsed = time.monotonic() - t0
    print(f"Готово за {elapsed:.1f} с: {EMAIL} / {PASSWORD}")
    print(f"Номеров: {len(rooms)}, броней: {booking_count}, расходов: {expense_count}, история: {HISTORY_DAYS} дней")


if __name__ == "__main__":
    main()
