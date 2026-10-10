"""Расчёт стоимости проживания и проверка ограничений по датам."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .db import all_

CENT = Decimal("0.01")


@dataclass
class Quote:
    total: Decimal
    nights: int
    nightly: list[tuple[date, Decimal]]
    min_stay: int
    closed_dates: list[date]
    base_total: Decimal = Decimal("0")        # сумма по ночам до тарифа, доплат и скидок
    plan_delta: Decimal = Decimal("0")        # на сколько тариф изменил сумму (± ₽)
    extra_guests: int = 0
    extra_guests_total: Decimal = Decimal("0")
    long_stay_percent: Decimal = Decimal("0")
    long_stay_discount: Decimal = Decimal("0")
    breakdown: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.closed_dates and self.nights >= self.min_stay


def nights_between(check_in: date, check_out: date) -> list[date]:
    return [check_in + timedelta(days=i) for i in range((check_out - check_in).days)]


def _money(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_plan(price: Decimal, plan: dict | None) -> Decimal:
    if not plan:
        return price
    return max(_money(price * (Decimal(1) + Decimal(plan["percent_delta"]) / 100) + Decimal(plan["fixed_delta"])), Decimal("0"))


def quote(conn, room_type: dict, check_in: date, check_out: date, guests: int | None = None,
          plan: dict | None = None) -> Quote:
    """Стоимость = сумма цен по ночам (цена на дату или базовая), с учётом тарифа (± % и ± ₽ за ночь),
    доплаты за гостей сверх включённых и скидки за длительность (неделя / месяц).
    Минимальный срок берётся по дате заезда; закрытая дата блокирует продажу."""
    rows = all_(
        conn,
        "SELECT date, price, min_stay, closed FROM rates"
        " WHERE room_type_id = %s AND date >= %s AND date < %s",
        (room_type["id"], check_in, check_out),
    )
    by_date = {r["date"]: r for r in rows}
    nightly, closed = [], []
    base_total = Decimal("0")
    for d in nights_between(check_in, check_out):
        r = by_date.get(d)
        price = Decimal(r["price"] if r and r["price"] is not None else room_type["base_price"])
        base_total += price
        nightly.append((d, apply_plan(price, plan)))
        if r and r["closed"]:
            closed.append(d)
    first = by_date.get(check_in)
    min_stay = first["min_stay"] if first and first["min_stay"] else room_type["min_stay"]
    nights = len(nightly)
    stay = sum((p for _, p in nightly), Decimal("0"))
    plan_delta = stay - base_total
    included = room_type.get("included_guests") or room_type.get("capacity") or 0
    extra = max((guests or 0) - included, 0) if included else 0
    extra_total = _money(Decimal(room_type.get("extra_guest_price") or 0) * extra * nights)
    month, week = Decimal(room_type.get("month_discount_percent") or 0), Decimal(room_type.get("week_discount_percent") or 0)
    pct = month if nights >= 28 and month > 0 else (week if nights >= 7 else Decimal("0"))
    discount = _money((stay + extra_total) * pct / 100) if pct else Decimal("0")
    total = stay + extra_total - discount
    breakdown = [{"label": f"{nights} {_nights_word(nights)} по тарифу категории", "amount": base_total}]
    if plan and plan_delta:
        breakdown.append({"label": f"Тариф «{plan['name']}»", "amount": plan_delta})
    if extra_total:
        breakdown.append({"label": f"Доплата за {extra} {_guests_word(extra)} сверх {included}", "amount": extra_total})
    if discount:
        breakdown.append({"label": f"Скидка за длительное проживание {pct:g}%", "amount": -discount})
    return Quote(total=total, nights=nights, nightly=nightly, min_stay=min_stay, closed_dates=closed,
                 base_total=base_total, plan_delta=plan_delta, extra_guests=extra, extra_guests_total=extra_total,
                 long_stay_percent=pct, long_stay_discount=discount, breakdown=breakdown)


def _nights_word(n: int) -> str:
    a, b = n % 10, n % 100
    return "ночь" if a == 1 and b != 11 else ("ночи" if 2 <= a <= 4 and not 12 <= b <= 14 else "ночей")


def _guests_word(n: int) -> str:
    """«за 1 гостя», «за 2 гостей», «за 21 гостя» (винительный падеж одушевлённого)."""
    return "гостя" if n % 10 == 1 and n % 100 != 11 else "гостей"
