"""Расчёт стоимости проживания и проверка ограничений по датам."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .db import all_


@dataclass
class Quote:
    total: Decimal
    nights: int
    nightly: list[tuple[date, Decimal]]
    min_stay: int
    closed_dates: list[date]

    @property
    def ok(self) -> bool:
        return not self.closed_dates and self.nights >= self.min_stay


def nights_between(check_in: date, check_out: date) -> list[date]:
    return [check_in + timedelta(days=i) for i in range((check_out - check_in).days)]


def quote(conn, room_type: dict, check_in: date, check_out: date) -> Quote:
    """Стоимость = сумма цен по ночам: цена на дату или базовая цена категории.
    Минимальный срок берётся по дате заезда; закрытая дата блокирует продажу."""
    rows = all_(
        conn,
        "SELECT date, price, min_stay, closed FROM rates"
        " WHERE room_type_id = %s AND date >= %s AND date < %s",
        (room_type["id"], check_in, check_out),
    )
    by_date = {r["date"]: r for r in rows}
    nightly, closed = [], []
    for d in nights_between(check_in, check_out):
        r = by_date.get(d)
        price = r["price"] if r and r["price"] is not None else room_type["base_price"]
        nightly.append((d, Decimal(price)))
        if r and r["closed"]:
            closed.append(d)
    first = by_date.get(check_in)
    min_stay = first["min_stay"] if first and first["min_stay"] else room_type["min_stay"]
    return Quote(
        total=sum((p for _, p in nightly), Decimal("0")),
        nights=len(nightly),
        nightly=nightly,
        min_stay=min_stay,
        closed_dates=closed,
    )
