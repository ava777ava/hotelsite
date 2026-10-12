"""Демо-данные для знакомства с системой: python -m app.demo
Создаёт аккаунт demo@fligel.ru / demo12345 с гостиницей на 12 номеров и бронями.
Также: администратор manager@fligel.ru, горничная anna@fligel.ru, собственник landlord@fligel.ru (пароль тот же)."""
import random
from datetime import date, timedelta

from . import modules
from .auth import hash_password, new_ical_token
from .db import all_, one, run, tx
from .expenses import create_default_categories
from .migrate import migrate

MALE = ["Алексей", "Андрей", "Антон", "Артём", "Виктор", "Владимир", "Дмитрий", "Евгений", "Игорь", "Илья", "Максим",
        "Михаил", "Николай", "Олег", "Павел", "Роман", "Сергей", "Тимур", "Юрий", "Ринат", "Ильдар", "Марат"]
FEMALE = ["Анна", "Анастасия", "Виктория", "Дарья", "Евгения", "Екатерина", "Елена", "Ирина", "Лариса", "Марина", "Мария",
          "Наталья", "Ольга", "Светлана", "Татьяна", "Юлия", "Алсу", "Гульнара", "Диана"]
SURNAMES = ["Иванов", "Петров", "Смирнов", "Кузнецов", "Попов", "Васильев", "Соколов", "Михайлов", "Новиков", "Фёдоров",
            "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев",
            "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев", "Григорьев",
            "Романов", "Воробьёв", "Сергеев", "Кузьмин", "Фролов", "Александров", "Дмитриев", "Королёв", "Гусев", "Киселёв"]


def make_guests(rnd: random.Random, n: int) -> list[str]:
    """Правдоподобные имена: мужские и женские фамилии согласованы по роду, имена не повторяются."""
    out: set[str] = set()
    while len(out) < n:
        sur = rnd.choice(SURNAMES)
        if rnd.random() < 0.5:
            out.add(f"{rnd.choice(MALE)} {sur}")
        else:
            out.add(f"{rnd.choice(FEMALE)} {sur}а" if not sur.endswith("ий") else f"{rnd.choice(FEMALE)} {sur[:-2]}ая")
    return sorted(out)


def main() -> None:
    migrate()
    rnd = random.Random(7)
    today = date.today()
    GUESTS = make_guests(rnd, 700)
    # один и тот же гость всегда с одним и тем же телефоном — иначе в «Истории гостя»
    # никогда не наберётся больше одного визита и «постоянных гостей» не появится
    guest_phones = {
        name: f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}"
        for name in GUESTS
    }
    with tx() as conn:
        if one(conn, "SELECT 1 FROM users WHERE email = 'demo@fligel.ru'"):
            print("Демо-аккаунт уже есть: demo@fligel.ru / demo12345 (также manager@, anna@, landlord@ — пароль тот же)")
            return
        acc = one(conn, "INSERT INTO accounts (name, plan, is_demo, modules) VALUES ('Гостиница «Флигель»', 'custom', true, %s) RETURNING id", (modules.KEYS,))["id"]
        run(conn, "INSERT INTO users (account_id, email, password_hash, name, role) VALUES (%s, %s, %s, %s, 'owner')",
            (acc, "demo@fligel.ru", hash_password("demo12345"), "Андрей"))
        for email, uname, role in (("manager@fligel.ru", "Марина (администратор)", "manager"), ("anna@fligel.ru", "Анна (горничная)", "housekeeper")):
            run(conn, "INSERT INTO users (account_id, email, password_hash, name, role) VALUES (%s, %s, %s, %s, %s)",
                (acc, email, hash_password("demo12345"), uname, role))
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
                # заявки с сайта «висят» только у будущих заездов — старые снимаются сами через REQUEST_TTL_HOURS
                status = "pending" if src == "direct" and d >= today and rnd.random() < 0.5 else "confirmed"
                guest = rnd.choice(GUESTS)
                total = price * nights
                run(conn, "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, source,"
                          " guest_name, guest_phone, guests_count, total_price, paid_amount)"
                          " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (acc, prop, rid, d, d + timedelta(days=nights), status, src, guest, guest_phones[guest],
                     rnd.choice([1, 2, 2]), total, total if status == "confirmed" and (d + timedelta(days=nights) <= today or rnd.random() < 0.6) else 0))
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
                # заявки с сайта «висят» только у будущих заездов — старые снимаются сами через REQUEST_TTL_HOURS
                status = "pending" if src == "direct" and d >= today and rnd.random() < 0.5 else "confirmed"
                guest = rnd.choice(GUESTS)
                total = price * nights
                run(conn, "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, source,"
                          " guest_name, guest_phone, guests_count, total_price, paid_amount)"
                          " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (acc, prop2, rid, d, d + timedelta(days=nights), status, src, guest, guest_phones[guest],
                     rnd.choice([1, 2]), total, total if status == "confirmed" and (d + timedelta(days=nights) <= today or rnd.random() < 0.6) else 0))
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
        # расходы, записанные на конкретные номера (стирка, мелкий ремонт, замена белья)
        for rid, _price in rooms[:6]:
            for _ in range(rnd.randint(2, 6)):
                run(conn, "INSERT INTO expenses (account_id, property_id, room_id, category_id, date, amount, comment)"
                          " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (acc, prop, rid, cats[rnd.choice(["Ремонт и обслуживание", "Расходники", "Уборка и прачечная"])],
                     today - timedelta(days=rnd.randint(1, 300)), rnd.randint(500, 6000), "Расход на номер"))
        # прочие доходы: завтраки, парковка, трансфер — часть на конкретных номерах
        inc_cats = {c["name"]: c["id"] for c in all_(conn, "SELECT id, name FROM income_categories WHERE account_id = %s",
                                                     (acc,))}
        for i in range(12):
            m = month_start
            for _ in range(i):
                m = (m - timedelta(days=1)).replace(day=1)
            for name, lo, hi in (("Завтраки и питание", 8000, 26000), ("Парковка", 3000, 9000),
                                 ("Трансфер", 0, 12000), ("Дополнительные услуги", 2000, 10000)):
                amount = rnd.randint(lo, hi)
                if amount:
                    run(conn, "INSERT INTO incomes (account_id, property_id, category_id, date, amount, comment)"
                              " VALUES (%s, %s, %s, %s, %s, %s)",
                        (acc, prop, inc_cats[name], m + timedelta(days=rnd.randint(2, 27)), amount, "За месяц"))
        for rid, _price in rooms[:3]:
            run(conn, "INSERT INTO incomes (account_id, property_id, room_id, category_id, date, amount, comment)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (acc, prop, rid, inc_cats["Штрафы и компенсации"], today - timedelta(days=rnd.randint(5, 120)),
                 rnd.randint(1000, 5000), "Компенсация за ущерб"))
        # шаблон повторяющегося расхода — аренда 1-го числа каждого месяца
        run(conn, "INSERT INTO expense_recurring_rules (account_id, category_id, amount, day_of_month, comment)"
                  " VALUES (%s, %s, %s, %s, %s)",
            (acc, cats["Аренда/ипотека"], 45000, 1, "Аренда офиса (автоматически)"))
        # комиссии площадок — для отчёта «чистая выручка по источникам»
        for channel, percent in (("avito", 12), ("yandex", 15), ("sutochno", 10)):
            run(conn, "INSERT INTO channel_commissions (account_id, channel, percent) VALUES (%s, %s, %s)",
                (acc, channel, percent))
        _seed_new_features(conn, rnd, acc, prop, prop2, rooms, rooms2, today)
    print("Готово: войдите как demo@fligel.ru / demo12345, страница бронирования — /book/demo")



def _seed_new_features(conn, rnd, acc, prop, prop2, rooms, rooms2, today) -> None:
    """Данные для новых функций, чтобы всё было видно сразу после входа: платежи, услуги, тарифы, теги и чёрный
    список, уборка, заметки на даты, группа номеров и переселение, собственник с комиссией УК."""
    from .api.guests import phone_key

    # --- платежи: оплата в брони превращается в историю (часть броней — предоплата и доплата отдельно)
    run(conn, "INSERT INTO booking_payments (account_id, booking_id, kind, amount, method, paid_on, note)"
              " SELECT account_id, id, 'payment', paid_amount, (ARRAY['cash', 'card', 'transfer', 'online'])[1 + floor(random() * 4)::int],"
              " least(check_in - 3 - (random() * 25)::int, current_date), '' FROM bookings WHERE paid_amount > 0 AND status = 'confirmed' AND random() < 0.7")
    run(conn, "INSERT INTO booking_payments (account_id, booking_id, kind, amount, method, paid_on, note)"
              " SELECT b.account_id, b.id, 'payment', round(b.paid_amount * 0.3), 'online', least(b.check_in - 10 - (random() * 20)::int, current_date), 'Предоплата'"
              " FROM bookings b WHERE b.paid_amount > 0 AND NOT EXISTS (SELECT 1 FROM booking_payments p WHERE p.booking_id = b.id)")
    run(conn, "INSERT INTO booking_payments (account_id, booking_id, kind, amount, method, paid_on, note)"
              " SELECT b.account_id, b.id, 'payment', b.paid_amount - round(b.paid_amount * 0.3), 'cash', least(b.check_in, current_date), 'Доплата при заселении'"
              " FROM bookings b WHERE b.paid_amount > 0 AND (SELECT count(*) FROM booking_payments p WHERE p.booking_id = b.id) = 1"
              " AND (SELECT p.note FROM booking_payments p WHERE p.booking_id = b.id) = 'Предоплата'")
    # --- справочник услуг и услуги в ближайших бронях
    for name, price in (("Завтрак", 500), ("Трансфер из аэропорта", 1800), ("Поздний выезд", 1000), ("Дополнительное место", 800)):
        run(conn, "INSERT INTO services (account_id, name, price) VALUES (%s, %s, %s)", (acc, name, price))
    upcoming = all_(conn, "SELECT id, check_in, check_out FROM bookings WHERE account_id = %s AND status = 'confirmed' AND check_in >= %s"
                          " AND check_in < %s ORDER BY check_in LIMIT 12", (acc, today, today + timedelta(days=10)))
    for i, b in enumerate(upcoming):
        if i % 3 == 0:
            run(conn, "INSERT INTO booking_services (account_id, booking_id, name, price, qty) VALUES (%s, %s, 'Завтрак', 500, %s)",
                (acc, b["id"], (b["check_out"] - b["check_in"]).days))
            run(conn, "UPDATE bookings SET total_price = total_price + 500 * %s WHERE id = %s", ((b["check_out"] - b["check_in"]).days, b["id"]))
        elif i % 3 == 1:
            run(conn, "UPDATE bookings SET discount_amount = 500, discount_reason = 'Постоянный гость', total_price = greatest(total_price - 500, 0),"
                      " deposit_amount = 3000, deposit_status = 'expected' WHERE id = %s", (b["id"],))
    # --- тарифы
    for rt in all_(conn, "SELECT id, name FROM room_types WHERE property_id = %s", (prop,)):
        run(conn, "INSERT INTO rate_plans (account_id, room_type_id, name, description, percent_delta, refundable, sort_order)"
                  " VALUES (%s, %s, 'Невозвратный', 'Скидка 10%%, отмена без возврата', -10, false, 1)", (acc, rt["id"]))
        run(conn, "INSERT INTO rate_plans (account_id, room_type_id, name, description, fixed_delta, breakfast, sort_order)"
                  " VALUES (%s, %s, 'С завтраком', 'Завтрак включён в стоимость', 500, true, 2)", (acc, rt["id"]))
        run(conn, "UPDATE room_types SET week_discount_percent = 5, month_discount_percent = 15 WHERE id = %s", (rt["id"],))
    # --- гости: теги, заметки, чёрный список, дни рождения
    frequent = all_(conn, f"SELECT right(regexp_replace(guest_phone, '\\D', '', 'g'), 10) AS k, (array_agg(guest_name))[1] AS name, count(*) AS n"
                          " FROM bookings WHERE account_id = %s AND guest_phone <> '' GROUP BY 1 ORDER BY n DESC, k LIMIT 8", (acc,))
    tag_sets = [(["vip", "постоянный"], "Любит тихий номер на верхнем этаже"), (["с собакой"], "Всегда с лабрадором, нужна миска"),
                (["командировка"], "Нужны документы для бухгалтерии"), (["поздний заезд"], "Обычно приезжает после 22:00"),
                (["vip"], ""), (["с детьми"], "Просит детскую кроватку")]
    for g, (tags, note) in zip(frequent, tag_sets):
        run(conn, "INSERT INTO guest_profiles (account_id, phone_key, name, tags, notes) VALUES (%s, %s, %s, %s, %s)", (acc, g["k"], g["name"], tags, note))
    if len(frequent) > 6:
        run(conn, "INSERT INTO guest_profiles (account_id, phone_key, name, notes, blacklisted, blacklist_reason) VALUES (%s, %s, %s, %s, true, %s)",
            (acc, frequent[6]["k"], frequent[6]["name"], "", "Курил в номере, не оплатил ущерб"))
    for b in all_(conn, "SELECT guest_phone, check_in FROM bookings WHERE account_id = %s AND status = 'confirmed' AND check_in BETWEEN %s AND %s"
                        " AND guest_phone <> '' ORDER BY check_in LIMIT 2", (acc, today + timedelta(days=1), today + timedelta(days=9))):
        run(conn, "INSERT INTO guest_profiles (account_id, phone_key, birthday) VALUES (%s, %s, %s)"
                  " ON CONFLICT (account_id, phone_key) DO UPDATE SET birthday = EXCLUDED.birthday",
            (acc, phone_key(b["guest_phone"]), date(1988, b["check_in"].month, b["check_in"].day)))
    # --- уборка: почти всё чисто, несколько номеров в разных состояниях
    run(conn, "UPDATE rooms SET cleaned_on = current_date WHERE account_id = %s", (acc,))
    staff = one(conn, "SELECT id FROM users WHERE email = 'anna@fligel.ru'")
    ids = [r[0] for r in rooms]
    run(conn, "UPDATE rooms SET cleaned_on = current_date - 2 WHERE id = ANY(%s::uuid[]) AND EXISTS (SELECT 1 FROM bookings b WHERE b.room_id = rooms.id"
              " AND b.check_out = current_date AND b.status = 'confirmed')", (ids,))
    run(conn, "UPDATE rooms SET hk_status = 'cleaning', hk_updated_at = now() WHERE id = %s", (ids[2],))
    run(conn, "UPDATE rooms SET hk_status = 'inspect', hk_updated_at = now() WHERE id = %s", (ids[4],))
    run(conn, "UPDATE rooms SET hk_status = 'repair', hk_note = 'Протекает кран в ванной', hk_updated_at = now() WHERE id = %s", (ids[7],))
    run(conn, "UPDATE rooms SET note = 'Ключ у администратора, диван раскладывается' WHERE id = %s", (ids[1],))
    if staff:
        run(conn, "UPDATE rooms SET hk_assigned_to = %s, hk_assigned_on = current_date WHERE id = ANY(%s::uuid[])", (staff["id"], ids[:6]))
    # --- заметки на даты
    for offset, text in ((4, "Праздник в городе: ждём много заездов, цены выше"), (9, "Проверка пожарной инспекции с 10:00")):
        run(conn, "INSERT INTO date_notes (account_id, property_id, day, text) VALUES (%s, %s, %s, %s)", (acc, prop, today + timedelta(days=offset), text))
    # --- группа из трёх номеров и переселение посреди проживания (даты после основной загрузки — свободны)
    import uuid as _uuid
    g = str(_uuid.uuid4())
    for rid, price in rooms[:3]:
        run(conn, "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, source, guest_name, guest_phone,"
                  " guests_count, total_price, group_id) VALUES (%s, %s, %s, %s, %s, 'confirmed', 'manual', 'Свадьба Кузнецовых', '+7 927 555-01-01',"
                  " 2, %s, %s)", (acc, prop, rid, today + timedelta(days=60), today + timedelta(days=62), price * 2, g))
    g2 = str(_uuid.uuid4())
    for rid, a, b_, total in ((rooms[3][0], 70, 73, 7500), (rooms[4][0], 73, 75, 5000)):
        run(conn, "INSERT INTO bookings (account_id, property_id, room_id, check_in, check_out, status, source, guest_name, guest_phone,"
                  " guests_count, total_price, group_id) VALUES (%s, %s, %s, %s, %s, 'confirmed', 'avito', 'Дмитрий Крылов', '+7 903 777-12-12',"
                  " 1, %s, %s)", (acc, prop, rid, today + timedelta(days=a), today + timedelta(days=b_), total, g2))
    # --- колокольчик и журнал действий
    for minutes, kind, text, link in ((12, "new_booking", "Новая заявка с сайта: Стандарт, заезд через 3 дня", "#/bookings"),
                                      (95, "room_issue", "Номер 108: поломка — Протекает кран в ванной", "#/cleaning"),
                                      (400, "sync_error", "Не удалось обновить календарь с площадки Авито: страница недоступна", "#/channels")):
        run(conn, "INSERT INTO notifications (account_id, kind, text, link, created_at) VALUES (%s, %s, %s, %s, now() - make_interval(mins => %s))",
            (acc, kind, text, link, minutes))
    run(conn, "UPDATE users SET notifications_seen_at = now() - interval '5 hours' WHERE account_id = %s", (acc,))
    owner = one(conn, "SELECT id FROM users WHERE email = 'demo@fligel.ru'")["id"]
    for hours, summary in ((30, "Добавлен сотрудник Марина (администратор) (manager)"), (29, "Подключён календарь площадки Авито"),
                           (6, "Изменены цены или ограничения: 14 записей"), (2, "Изменены настройки объекта «Гостиница «Флигель»»")):
        run(conn, "INSERT INTO audit_log (account_id, user_id, action, summary, created_at) VALUES (%s, %s, 'demo', %s, now() - make_interval(hours => %s))",
            (acc, owner, summary, hours))
    # --- собственник квартир и комиссия управляющей компании
    run(conn, "UPDATE properties SET mc_commission_percent = 15, mc_commission_base = 'net' WHERE id = %s", (prop2,))
    lid = one(conn, "INSERT INTO users (account_id, email, password_hash, name, role) VALUES (%s, 'landlord@fligel.ru', %s, 'Пётр (собственник квартир)', 'landlord') RETURNING id",
              (acc, hash_password("demo12345")))["id"]
    run(conn, "INSERT INTO user_properties (account_id, user_id, property_id) VALUES (%s, %s, %s)", (acc, lid, prop2))
    # --- «когда создана бронь»: у каждого канала своё окно бронирования, будущие брони появились за последние ~2 недели
    #     (иначе все брони были бы «созданы сегодня», и аналитика темпа и окна показывала бы пустоту)
    run(conn, """UPDATE bookings SET created_at = least(
                   check_in::timestamptz + interval '10 hours' - interval '1 day' * (CASE source
                       WHEN 'direct' THEN 8 + mod(abs(hashtext(id::text)), 30) WHEN 'yandex' THEN 5 + mod(abs(hashtext(id::text)), 25)
                       WHEN 'avito' THEN 1 + mod(abs(hashtext(id::text)), 14) WHEN 'sutochno' THEN 2 + mod(abs(hashtext(id::text)), 20)
                       ELSE mod(abs(hashtext(id::text)), 10) END),
                   now() - interval '1 day' * (mod(abs(hashtext(id::text || 'x')), 13)) - interval '1 hour')
               WHERE account_id = %s AND status <> 'blocked'""", (acc,))
    _seed_autopilot(conn, acc, prop, today)
    _seed_household(conn, acc, prop, today)


def _seed_household(conn, acc, prop, today) -> None:
    """Склад, счётчики с историей и инвентарь — чтобы раздел «Хозяйство» не был пустым на демо."""
    from decimal import Decimal
    from .household import move
    anna = one(conn, "SELECT id FROM users WHERE email = 'anna@fligel.ru'")["id"]
    for name, unit, qty, mn, norm in (("Мыло жидкое", "шт", 24, 6, 1), ("Шампунь (саше)", "шт", 150, 40, 2), ("Пакеты для мусора", "рул", 5, 3, 0.25),
                                       ("Туалетная бумага", "рул", 60, 24, 2), ("Чай и кофе (набор)", "шт", 90, 30, 1)):
        it = one(conn, "INSERT INTO stock_items (account_id, property_id, name, unit, quantity, min_quantity, norm_per_cleaning) VALUES (%s, %s, %s, %s, 0, %s, %s) RETURNING id",
                 (acc, prop, name, unit, mn, norm))
        move(conn, acc, it["id"], Decimal(qty) + Decimal("20"), "in", "Закупка", None)
        move(conn, acc, it["id"], -Decimal("20"), "cleaning", "Уборка номеров за неделю", anna)
    # счётчики: общий (холодная вода) и по двум номерам (электричество), показания раз в месяц за полгода
    rooms = all_(conn, "SELECT id, name FROM rooms WHERE account_id = %s AND property_id = %s ORDER BY sort_order LIMIT 2", (acc, prop))
    cat = one(conn, "SELECT id FROM expense_categories WHERE account_id = %s AND lower(name) = 'коммунальные услуги'", (acc,))
    owner = one(conn, "SELECT id FROM users WHERE email = 'demo@fligel.ru'")["id"]
    for kind, room, unit, tariff, start, step in (("water_cold", None, "м³", Decimal("48.5"), Decimal("1200"), Decimal("38")),
                                                  ("electricity", rooms[0], "кВт·ч", Decimal("6.2"), Decimal("8400"), Decimal("310")),
                                                  ("electricity", rooms[1], "кВт·ч", Decimal("6.2"), Decimal("7900"), Decimal("270"))):
        m = one(conn, "INSERT INTO meters (account_id, property_id, room_id, kind, unit, tariff) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (acc, prop, room["id"] if room else None, kind, unit, tariff))
        value, prev = start, None
        for k in range(6, -1, -1):
            day = today - timedelta(days=30 * k)
            if prev is not None:
                value += step + Decimal(k * 3)
            cons = value - prev if prev is not None else Decimal("0")
            cost = (cons * tariff).quantize(Decimal("0.01"))
            exp_id = None
            if cost > 0 and cat:
                exp_id = one(conn, "INSERT INTO expenses (account_id, property_id, room_id, category_id, date, amount, comment, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                             (acc, prop, room["id"] if room else None, cat["id"], day, cost, f"Счётчик: {cons} {unit} × {tariff} ₽", owner))["id"]
            run(conn, "INSERT INTO meter_readings (account_id, meter_id, date, value, consumption, tariff, cost, expense_id, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (acc, m["id"], day, value, cons, tariff, cost, exp_id, owner))
            prev = value
    # инвентарь типового номера и одна проверка после выезда
    std = all_(conn, "SELECT r.id FROM rooms r JOIN room_types rt ON rt.id = r.room_type_id WHERE r.account_id = %s AND r.property_id = %s AND rt.name = 'Стандарт' ORDER BY r.sort_order", (acc, prop))
    for r in std:
        for i, (name, qty) in enumerate((("Чайник", 1), ("Фен", 1), ("Полотенца банные", 4), ("Халат", 2), ("Плед", 1), ("Пульт от телевизора", 1))):
            run(conn, "INSERT INTO inventory_items (account_id, room_id, name, qty, sort_order) VALUES (%s, %s, %s, %s, %s)", (acc, r["id"], name, qty, i))
    if std:
        chk = one(conn, "INSERT INTO inventory_checks (account_id, room_id, user_id, problems, created_at) VALUES (%s, %s, %s, 1, now() - interval '1 day') RETURNING id", (acc, std[0]["id"], anna))
        run(conn, "INSERT INTO inventory_check_items (check_id, name, qty, state, note) VALUES (%s, 'Фен', 1, 'broken', 'Не включается')", (chk["id"],))


def _seed_autopilot(conn, acc, prop, today) -> None:
    """Автопилот, задачи, анкеты и отзывы — чтобы разделы не были пустыми на демо."""
    from . import automation, guestlinks
    from .api.tasks import create_task
    automation.ensure_presets(conn, acc, use_defaults=True)
    run(conn, "UPDATE automation_rules SET enabled = true WHERE account_id = %s AND preset IN ('questionnaire', 'review_request')", (acc,))
    anna = one(conn, "SELECT id FROM users WHERE email = 'anna@fligel.ru'")["id"]
    owner = one(conn, "SELECT id FROM users WHERE email = 'demo@fligel.ru'")["id"]
    first_room = one(conn, "SELECT id FROM rooms WHERE account_id = %s ORDER BY sort_order, name LIMIT 1", (acc,))["id"]
    create_task(conn, acc, "Заменить лампочку в ванной", assignee_id=anna, due_date=today - timedelta(days=2), room_id=first_room, created_by=owner)
    create_task(conn, acc, "Принять бельё из прачечной", due_date=today, created_by=owner)
    create_task(conn, acc, "Проверить огнетушители и аптечки", description="Срок годности, пломбы на огнетушителях. Отметить в журнале.",
                due_date=today + timedelta(days=5), recurrence="monthly", created_by=owner)
    done = create_task(conn, acc, "Купить средство для стёкол", assignee_id=anna, due_date=today - timedelta(days=1), created_by=owner)
    run(conn, "UPDATE tasks SET done_at = now() - interval '20 hours', done_by = %s WHERE id = %s", (anna, done["id"]))
    run(conn, "UPDATE rooms SET door_code = '4821#' WHERE id = %s", (first_room,))
    # анкеты: у двух ближайших заездов гость уже ответил
    for i, b in enumerate(all_(conn, "SELECT * FROM bookings WHERE account_id = %s AND status = 'confirmed' AND check_in BETWEEN %s AND %s"
                                     " ORDER BY check_in LIMIT 3", (acc, today + timedelta(days=1), today + timedelta(days=9)))):
        run(conn, "UPDATE bookings SET door_code = %s WHERE id = %s", (f"{1200 + i * 111}*", b["id"]))
        if i < 2:
            tok = guestlinks.ensure_form(conn, acc, b["id"])
            run(conn, "UPDATE booking_forms SET arrival_time = %s, guests_count = %s, wishes = %s, car_number = %s, filled_at = now() - interval '3 hours' WHERE token = %s",
                (("18:30", "21:00")[i], 2, ("Детская кроватка и поздний заезд", "")[i], ("А123ВБ 116", "")[i], tok))
    # отзывы о прошедших проживаниях и журнал автопилота
    ratings = [(5, "Всё отлично, чисто и уютно"), (4, "Хорошо, но тонкие стены"), (2, "Шумно по ночам, плохо спали"), (5, ""), (3, "Нормально, wi-fi медленный"), (5, "Вернёмся")]
    past = all_(conn, "SELECT * FROM bookings WHERE account_id = %s AND status = 'confirmed' AND check_out < %s ORDER BY check_out DESC LIMIT %s",
                (acc, today, len(ratings)))
    for b, (rating, comment) in zip(past, ratings):
        tok = guestlinks.ensure_review(conn, b)
        run(conn, "UPDATE reviews SET rating = %s, comment = %s, submitted_at = now() - make_interval(days => %s) WHERE token = %s",
            (rating, comment, (b["check_out"] - today).days * -1, tok))
    rule = {r["preset"]: r["id"] for r in all_(conn, "SELECT id, preset FROM automation_rules WHERE account_id = %s", (acc,))}
    for b, (key, status, detail) in zip(past, (("review_request", "done", "Письмо отправлено"), ("cleaning_after_checkout", "done", "Номер: нужна уборка"),
                                               ("checkin_instructions", "skipped", "У гостя нет email — письмо не отправлено, сотрудникам отправлено напоминание"),
                                               ("debt_alert", "done", "Сообщение сотрудникам отправлено"))):
        run(conn, "INSERT INTO automation_runs (account_id, rule_id, booking_id, status, detail, created_at) VALUES (%s, %s, %s, %s, %s, now() - interval '1 day')"
                  " ON CONFLICT DO NOTHING", (acc, rule[key], b["id"], status, detail))

if __name__ == "__main__":
    main()


def reset_if_due(now=None) -> bool:
    """Ежедневный сброс публичной песочницы: после DEMO_RESET_HOUR один раз в день демо-аккаунт пересоздаётся с чистыми данными.
    Работает, только если включено DEMO_ENABLED и демо-аккаунт уже создан."""
    from datetime import datetime
    from . import config
    if not config.DEMO_ENABLED:
        return False
    now = now or datetime.now()
    today = now.date().isoformat()
    with tx() as conn:
        if now.hour < config.DEMO_RESET_HOUR:
            return False
        st = one(conn, "SELECT value FROM service_state WHERE key = 'demo_reset_on'")
        if st and st["value"] == today:
            return False
        run(conn, "INSERT INTO service_state (key, value) VALUES ('demo_reset_on', %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()", (today,))
        had = one(conn, "SELECT 1 FROM accounts WHERE is_demo")
        run(conn, "DELETE FROM accounts WHERE is_demo")
    if had:
        main()
    return bool(had)
