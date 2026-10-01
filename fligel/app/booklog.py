"""История изменений брони: запись событий и человекочитаемое описание правок."""
import json
from decimal import Decimal

from .db import all_, run

FIELD_LABELS = {
    "room_id": "Номер", "check_in": "Заезд", "check_out": "Выезд", "status": "Статус", "source": "Источник",
    "guest_name": "Гость", "guest_phone": "Телефон", "guest_email": "Email", "guests_count": "Гостей",
    "total_price": "Стоимость", "paid_amount": "Оплачено", "notes": "Комментарий",
}
STATUS_LABELS = {"confirmed": "Подтверждена", "pending": "Ждёт оплаты", "blocked": "Даты закрыты",
                 "cancelled": "Отменена"}
SOURCE_LABELS = {"manual": "Вручную", "direct": "Сайт", "avito": "Авито", "yandex": "Яндекс", "sutochno": "Суточно",
                 "ostrovok": "Островок", "other": "Другое"}


def log(conn, account_id, booking_id, user_id, action: str, details: dict | None = None) -> None:
    run(conn, "INSERT INTO booking_log (account_id, booking_id, user_id, action, details) VALUES (%s, %s, %s, %s, %s)",
        (account_id, booking_id, user_id, action, json.dumps(details or {}, ensure_ascii=False, default=str)))


def _show(field: str, value, room_names: dict) -> str:
    if value is None or value == "":
        return "—"
    if field == "room_id":
        return room_names.get(str(value), "—")
    if field == "status":
        return STATUS_LABELS.get(value, str(value))
    if field == "source":
        return SOURCE_LABELS.get(value, str(value))
    if field in ("check_in", "check_out"):
        return value.strftime("%d.%m.%Y")
    if field in ("total_price", "paid_amount"):
        return f"{Decimal(value):.0f} ₽"
    return str(value)


def diff(conn, old: dict, new: dict) -> list[dict]:
    """Список изменений между старым и новым состоянием брони: [{"field", "from", "to"}]."""
    changed = [k for k in FIELD_LABELS if k in old and k in new and (
        (Decimal(old[k]) != Decimal(new[k])) if k in ("total_price", "paid_amount") else old[k] != new[k])]
    if not changed:
        return []
    room_names: dict = {}
    if "room_id" in changed:
        ids = [str(old["room_id"]), str(new["room_id"])]
        room_names = {str(r["id"]): f"№{r['name']}" for r in all_(
            conn, "SELECT id, name FROM rooms WHERE id = ANY(%s::uuid[])", (ids,))}
    return [{"field": FIELD_LABELS[k], "from": _show(k, old[k], room_names), "to": _show(k, new[k], room_names)}
            for k in changed]
