"""Бизнес-логика расходов: стандартные категории и генерация повторяющихся расходов."""
from datetime import date

from .db import all_, run, tx

# Цвета взяты из палитры интерфейса (app.css), чтобы категории смотрелись как часть системы.
DEFAULT_EXPENSE_CATEGORIES = [
    ("Уборка и прачечная", "#23767E"),
    ("Коммунальные услуги", "#4A5A6A"),
    ("Комиссии площадок", "#6E4A93"),
    ("Ремонт и обслуживание", "#B4562E"),
    ("Расходники", "#B7791F"),
    ("Зарплата", "#2F5D50"),
    ("Аренда/ипотека", "#5E6B5A"),
    ("Налоги", "#7A3418"),
    ("Реклама", "#8A5A12"),
    ("Прочее", "#69755F"),
]


def create_default_categories(conn, account_id: str) -> None:
    for i, (name, color) in enumerate(DEFAULT_EXPENSE_CATEGORIES):
        run(
            conn,
            "INSERT INTO expense_categories (account_id, name, color, sort_order) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (account_id, lower(name)) WHERE NOT archived DO NOTHING",
            (account_id, name, color, i),
        )


def generate_due_expenses(today: date | None = None) -> int:
    """Создаёт расходы по активным шаблонам за текущий месяц, если срок наступил и ещё не создано.

    Вызывается из того же фонового планировщика, что и синхронизация iCal (app/sync.py).
    Защита от дублей — уникальный индекс (recurring_rule_id, recurring_period) в БД:
    повторный запуск в тот же день или в тот же месяц ничего не создаст ещё раз.
    """
    today = today or date.today()
    period = today.strftime("%Y-%m")
    created = 0
    with tx() as conn:
        rules = all_(conn, "SELECT * FROM expense_recurring_rules WHERE active AND day_of_month <= %s",
                     (today.day,))
        for r in rules:
            created += run(
                conn,
                "INSERT INTO expenses (account_id, property_id, room_id, category_id, date, amount, comment,"
                " recurring_rule_id, recurring_period) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (recurring_rule_id, recurring_period) WHERE recurring_rule_id IS NOT NULL DO NOTHING",
                (r["account_id"], r["property_id"], r["room_id"], r["category_id"],
                 date(today.year, today.month, r["day_of_month"]), r["amount"], r["comment"], r["id"], period),
            )
    return created
