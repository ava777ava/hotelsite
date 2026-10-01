"""Импорт броней из CSV (переезд из Excel, RealtyCalendar и т. п.).

Чистая разборка таблицы без обращения к БД: по заголовкам находит колонки (русские и
английские названия), приводит даты и суммы к нужному виду и возвращает строки с ошибками."""
import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

MAX_ROWS = 2000
MAX_BYTES = 1_500_000

# синонимы заголовков → внутреннее имя поля
HEADERS = {
    "check_in": ("заезд", "дата заезда", "приезд", "check_in", "checkin", "arrival", "с"),
    "check_out": ("выезд", "дата выезда", "отъезд", "check_out", "checkout", "departure", "по"),
    "room": ("номер", "комната", "апартаменты", "room", "объект размещения"),
    "guest_name": ("гость", "имя", "фио", "клиент", "guest", "name"),
    "guest_phone": ("телефон", "тел", "phone"),
    "guest_email": ("email", "e-mail", "почта", "эл. почта"),
    "guests_count": ("гостей", "кол-во гостей", "количество гостей", "guests"),
    "total_price": ("стоимость", "сумма", "цена", "итого", "total", "price"),
    "paid_amount": ("оплачено", "предоплата", "paid"),
    "source": ("источник", "канал", "source"),
    "notes": ("комментарий", "примечание", "заметка", "notes", "comment"),
}
SOURCE_WORDS = {
    "авито": "avito", "avito": "avito", "яндекс": "yandex", "yandex": "yandex", "суточно": "sutochno",
    "sutochno": "sutochno", "островок": "ostrovok", "ostrovok": "ostrovok", "сайт": "direct",
    "прямая": "direct", "direct": "direct", "вручную": "manual", "manual": "manual", "телефон": "manual",
}
TEMPLATE = ("Заезд;Выезд;Номер;Гость;Телефон;Email;Гостей;Источник;Стоимость;Оплачено;Комментарий\n"
            "15.07.2026;18.07.2026;101;Иван Петров;+7 900 111-22-33;;2;Авито;10500;3000;Просил поздний заезд\n")


def parse_any_date(raw: str) -> date | None:
    s = (raw or "").strip()[:10].strip()
    for pat, order in ((r"^(\d{4})-(\d{1,2})-(\d{1,2})$", "ymd"), (r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", "dmy"),
                       (r"^(\d{1,2})[./](\d{1,2})[./](\d{2})$", "dmy2")):
        m = re.match(pat, s)
        if not m:
            continue
        a, b, c = (int(x) for x in m.groups())
        try:
            if order == "ymd":
                return date(a, b, c)
            return date(c + (2000 if order == "dmy2" else 0), b, a)
        except ValueError:
            return None
    return None


def parse_amount(raw: str) -> Decimal | None:
    s = re.sub(r"[\s ₽рРуб.]*$", "", (raw or "").strip()).replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        return Decimal("0")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d >= 0 else None


def read_table(text: str) -> tuple[list[str], list[dict]]:
    """Возвращает (найденные поля, строки как словари внутренних имён + _line). Бросает ValueError с русским текстом."""
    text = text.lstrip("﻿")
    if not text.strip():
        raise ValueError("Файл пустой")
    head = text.splitlines()[0]
    delim = max((";", ",", "\t"), key=head.count)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader]
    if not rows:
        raise ValueError("Файл пустой")
    names = [c.strip().lower() for c in rows[0]]
    cols: dict[str, int] = {}
    for field, words in HEADERS.items():
        for i, n in enumerate(names):
            if n in words and i not in cols.values():
                cols[field] = i
                break
    for need, label in (("check_in", "Заезд"), ("check_out", "Выезд"), ("room", "Номер")):
        if need not in cols:
            raise ValueError(f"Не найдена колонка «{label}». Первая строка файла должна содержать заголовки "
                             "(например: Заезд;Выезд;Номер;Гость;Телефон;Стоимость). Скачайте образец.")
    body = rows[1:]
    if len(body) > MAX_ROWS:
        raise ValueError(f"В файле больше {MAX_ROWS} строк — разбейте его на части")
    out = []
    for n, r in enumerate(body, start=2):
        if not any(c.strip() for c in r):
            continue
        item = {f: (r[i].strip() if i < len(r) else "") for f, i in cols.items()}
        item["_line"] = n
        out.append(item)
    return list(cols), out


def normalize(item: dict) -> tuple[dict | None, str | None]:
    """Приводит строку к полям брони или возвращает текст ошибки."""
    ci, co = parse_any_date(item.get("check_in", "")), parse_any_date(item.get("check_out", ""))
    if not ci:
        return None, "не понятна дата заезда (нужно ДД.ММ.ГГГГ)"
    if not co:
        return None, "не понятна дата выезда (нужно ДД.ММ.ГГГГ)"
    if co <= ci:
        return None, "выезд должен быть позже заезда"
    if (co - ci).days > 366:
        return None, "слишком длинный срок проживания"
    total = parse_amount(item.get("total_price", ""))
    if total is not None and not item.get("total_price", "").strip():
        total = "auto"  # цена не указана — посчитаем по тарифам номера
    paid = parse_amount(item.get("paid_amount", ""))
    if total is None:
        return None, "стоимость — не число"
    if paid is None:
        return None, "«Оплачено» — не число"
    try:
        guests = int(re.sub(r"\D", "", item.get("guests_count", "")) or 1) or 1
    except ValueError:
        guests = 1
    src = SOURCE_WORDS.get(item.get("source", "").strip().lower(), "manual" if not item.get("source") else "other")
    return {"check_in": ci, "check_out": co, "room": item.get("room", "").strip(), "guest_name": item.get("guest_name", "")[:200],
            "guest_phone": item.get("guest_phone", "")[:50], "guest_email": item.get("guest_email", "")[:200],
            "guests_count": min(guests, 50), "total_price": total, "paid_amount": paid, "source": src,
            "notes": item.get("notes", "")[:2000]}, None
