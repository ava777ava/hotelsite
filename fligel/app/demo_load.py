"""Нагрузочные демо-данные: по умолчанию 70 номеров и 2 года броней и расходов; можно больше.

Отдельный аккаунт (не трогает обычные демо-данные из app/demo.py) — нужен, чтобы проверить,
что шахматка, отчёты и списки броней открываются быстро на реалистично большом объёме данных.

Запуск: python -m app.demo_load [--rooms 500] [--years 3]
Замеры скорости экранов и запросов на этих данных: python tests/perf_check.py (нужен работающий сервер).
"""
import argparse
import random
import time
from datetime import date, timedelta

from . import modules
from .auth import hash_password, new_ical_token
from .db import all_, one, run, tx
from .expenses import create_default_categories
from .migrate import migrate

EMAIL = "loadtest@fligel.ru"
PASSWORD = "loadtest12345"
HISTORY_DAYS = 730  # 2 года


def main(rooms_total: int = 70, years: int = 2) -> None:
    migrate()
    history_days = 365 * years
    rnd = random.Random(42)
    today = date.today()
    t0 = time.monotonic()
    with tx() as conn:
        if one(conn, "SELECT 1 FROM users WHERE email = %s", (EMAIL,)):
            print(f"Нагрузочный аккаунт уже есть: {EMAIL} / {PASSWORD}")
            return
        acc = one(conn, "INSERT INTO accounts (name, modules) VALUES ('Нагрузочный тест: Большой отель', %s) RETURNING id", (modules.KEYS,))["id"]
        run(conn, "INSERT INTO users (account_id, email, password_hash, name, role) VALUES (%s, %s, %s, %s, 'owner')",
            (acc, EMAIL, hash_password(PASSWORD), "Нагрузочный владелец"))
        prop = one(conn, "INSERT INTO properties (account_id, name, address, phone, public_slug) VALUES"
                         " (%s, 'Большой отель', 'Москва, Тестовая ул., 1', '+7 900 000-11-22', 'loadtest')"
                         " RETURNING id", (acc,))["id"]

        rooms: list[tuple[str, int]] = []
        share = [("Стандарт", 30, 3000, 2), ("Комфорт", 20, 4200, 2), ("Делюкс", 12, 6000, 3), ("Люкс", 6, 9500, 4), ("Апартаменты", 2, 15000, 6)]
        categories = [(n, max(1, round(c * rooms_total / 70)), p, cap) for n, c, p, cap in share]
        categories[0] = (categories[0][0], categories[0][1] + rooms_total - sum(c[1] for c in categories), categories[0][2], categories[0][3])
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
        assert len(rooms) == rooms_total, (len(rooms), rooms_total)

        sources = ["avito", "avito", "yandex", "yandex", "direct", "manual", "sutochno"]
        booking_count = 0
        batch: list[tuple] = []
        with conn.cursor() as cur:
            def flush() -> None:
                if batch:
                    cur.executemany("INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, source, guest_name,"
                                    " guest_phone, guests_count, total_price, paid_amount, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", batch)
                    batch.clear()
            for rid, price in rooms:
                d = today - timedelta(days=history_days)
                while d < today + timedelta(days=40):
                    d += timedelta(days=rnd.randint(0, 3))
                    nights = rnd.choice([1, 2, 2, 3, 3, 4, 5, 7])
                    src = rnd.choice(sources)
                    status = "pending" if src == "direct" and rnd.random() < 0.5 and d >= today else "confirmed"
                    total = price * nights
                    created = min(d - timedelta(days=rnd.randint(0, 30)), today)
                    batch.append((acc, prop, rid, d, d + timedelta(days=nights), status, src, f"Гость {rnd.randint(1, 4000)}",
                                  f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
                                  rnd.choice([1, 2]), total, total if status == "confirmed" and rnd.random() < 0.6 else 0, created))
                    booking_count += 1
                    d += timedelta(days=nights)
                    if len(batch) >= 5000:
                        flush()
            flush()

        create_default_categories(conn, acc)
        cats = {c["name"]: c["id"] for c in all_(conn, "SELECT id, name FROM expense_categories WHERE account_id = %s",
                                                 (acc,))}
        month_start = today.replace(day=1)
        expense_count = 0
        for i in range(12 * years):
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
    print(f"Номеров: {len(rooms)}, броней: {booking_count}, расходов: {expense_count}, история: {history_days} дней")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rooms", type=int, default=70)
    ap.add_argument("--years", type=int, default=2)
    args = ap.parse_args()
    main(args.rooms, args.years)
