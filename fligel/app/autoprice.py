"""Автоцены: правила → предлагаемые цены на ближайшие дни → (по выбору владельца) применяются сами.

Режимы: off — ничего не считается; suggest — предложения лежат в списке, цены меняет человек одним нажатием;
auto — цены записываются в календарь цен сами, каждое изменение попадает в журнал (price_changes).

Базовая цена даты — ручная цена из календаря, если её поставил человек, иначе базовая цена категории. «Ручной» считается цена,
которая не совпадает с последней автоматической записью журнала — поэтому автоцены не накладываются друг на друга и не
перебивают то, что владелец задал вручную. Когда условие правила перестало выполняться, цена автоматически возвращается к базовой."""
import logging
from datetime import date, timedelta
from decimal import Decimal

from . import audit, calendar_ru, notify
from .db import all_, one, run, tx

log = logging.getLogger("fligel.autoprice")

KINDS = {
    "low_occupancy": "Низкая загрузка ближайших дней — снизить цену",
    "weekend": "Выходные (пятница и суббота) — поднять цену",
    "holiday": "Праздничные даты — поднять цену",
    "last_room": "Остался последний свободный номер категории — поднять цену",
}
PREVIEW_LIMIT = 400


def _round10(v: Decimal) -> Decimal:
    return (v / 10).quantize(Decimal("1")) * 10


def _reason(rule: dict, occ: float | None, d: date) -> str:
    pct = Decimal(rule["percent"])
    sign = f"{pct:+.0f} %".replace("+", "+")
    if rule["kind"] == "low_occupancy":
        return f"низкая загрузка ({occ:.0f} % < {rule['threshold']} %): {sign}"
    if rule["kind"] == "weekend":
        return f"выходной: {sign}"
    if rule["kind"] == "holiday":
        return f"{calendar_ru.holiday_name(d).lower()}: {sign}"
    return f"остался последний номер: {sign}"


def compute(conn, account_id, today: date | None = None, horizon: int | None = None) -> list[dict]:
    """Предлагаемые изменения цен: [{room_type_id, type_name, date, current_price, suggested_price, reasons}]. Ничего не пишет."""
    today = today or date.today()
    st = one(conn, "SELECT horizon_days FROM price_settings WHERE account_id = %s", (account_id,))
    horizon = horizon or (st["horizon_days"] if st else 60)
    rules = all_(conn, "SELECT * FROM price_rules WHERE account_id = %s AND enabled", (account_id,))
    end = today + timedelta(days=horizon)
    types = all_(conn, "SELECT rt.id, rt.name, rt.base_price, rt.min_price, rt.max_price,"
                       " (SELECT count(*) FROM rooms r WHERE r.room_type_id = rt.id) AS rooms FROM room_types rt WHERE rt.account_id = %s", (account_id,))
    rates = {(str(r["room_type_id"]), r["date"]): r for r in all_(
        conn, "SELECT room_type_id, date, price, closed FROM rates WHERE account_id = %s AND date >= %s AND date < %s", (account_id, today, end))}
    busy: dict[tuple, int] = {}
    for r in all_(conn, "SELECT r.room_type_id, g::date AS day, count(DISTINCT b.room_id) AS n FROM bookings b JOIN rooms r ON r.id = b.room_id"
                        " CROSS JOIN LATERAL generate_series(greatest(b.check_in, %s::date), least(b.check_out - 1, %s::date), interval '1 day') g"
                        " WHERE b.account_id = %s AND b.status IN ('confirmed', 'pending', 'blocked') AND b.check_in < %s AND b.check_out > %s"
                        " GROUP BY r.room_type_id, g::date", (today, end - timedelta(days=1), account_id, end, today)):
        busy[(str(r["room_type_id"]), r["day"])] = r["n"]
    # последняя автоматическая цена по (категория, дата) — чтобы отличать её от ручной
    last_auto = {(str(r["room_type_id"]), r["date"]): r for r in all_(
        conn, "SELECT DISTINCT ON (room_type_id, date) room_type_id, date, new_price, base_price FROM price_changes"
              " WHERE account_id = %s AND date >= %s AND date < %s ORDER BY room_type_id, date, created_at DESC", (account_id, today, end))}
    out = []
    for t in types:
        tid = str(t["id"])
        t_rules = [r for r in rules if r["room_type_id"] is None or str(r["room_type_id"]) == tid]
        if not t["rooms"]:
            continue
        for i in range((end - today).days):
            day = today + timedelta(days=i)
            rate = rates.get((tid, day))
            if rate and rate["closed"]:
                continue
            current = Decimal(rate["price"]) if rate and rate["price"] is not None else Decimal(t["base_price"])
            journal = last_auto.get((tid, day))
            auto_owned = rate is not None and rate["price"] is not None and journal is not None and Decimal(journal["new_price"]) == Decimal(rate["price"])
            if auto_owned and journal["base_price"] is not None:
                base = Decimal(journal["base_price"])           # цена, от которой считали в прошлый раз (ручная или базовая)
            elif rate is None or rate["price"] is None or auto_owned:
                base = Decimal(t["base_price"])
            else:
                base = Decimal(rate["price"])                   # цену поставил человек — считаем от неё
            n_busy = busy.get((tid, day), 0)
            occ = n_busy * 100 / t["rooms"]
            pct = Decimal("0")
            reasons = []
            for r in t_rules:
                hit = False
                if r["kind"] == "weekend":
                    hit = day.weekday() in (4, 5)
                elif r["kind"] == "holiday":
                    hit = bool(calendar_ru.holiday_name(day))
                elif r["kind"] == "low_occupancy":
                    hit = i <= r["days_ahead"] and occ < r["threshold"]
                elif r["kind"] == "last_room":
                    hit = t["rooms"] >= 2 and t["rooms"] - n_busy == 1
                if hit:
                    pct += Decimal(r["percent"])
                    reasons.append(_reason(r, occ, day))
            if not reasons and not auto_owned:
                continue
            target = _round10(base * (1 + pct / 100)) if reasons else base
            lo = Decimal(t["min_price"]) if t["min_price"] is not None else None
            hi = Decimal(t["max_price"]) if t["max_price"] is not None else None
            if lo is not None and hi is not None and lo > hi:
                lo = hi = None  # перепутаны границы — не ограничиваем, а не ломаем цены
            if lo is not None and target < lo:
                target = lo
                reasons.append(f"не ниже минимума {lo:.0f} ₽")
            if hi is not None and target > hi:
                target = hi
                reasons.append(f"не выше максимума {hi:.0f} ₽")
            if target < 0:
                target = Decimal("0")
            if abs(target - current) < 1:
                continue
            out.append({"room_type_id": t["id"], "type_name": t["name"], "date": day, "current_price": current, "suggested_price": target, "base_price": base,
                        "reasons": "; ".join(reasons) if reasons else "условия правил больше не выполняются — возвращаем базовую цену"})
    return out


def _apply_one(conn, account_id, s: dict, source: str, user_id=None) -> None:
    old = one(conn, "SELECT price FROM rates WHERE room_type_id = %s AND date = %s", (s["room_type_id"], s["date"]))
    run(conn, "INSERT INTO rates (account_id, room_type_id, date, price) VALUES (%s, %s, %s, %s)"
              " ON CONFLICT (room_type_id, date) DO UPDATE SET price = EXCLUDED.price",
        (account_id, s["room_type_id"], s["date"], s["suggested_price"]))
    run(conn, "INSERT INTO price_changes (account_id, room_type_id, date, old_price, new_price, base_price, reasons, source, user_id)"
              " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (account_id, s["room_type_id"], s["date"], old["price"] if old else None, s["suggested_price"], s.get("base_price"), s["reasons"][:500], source, user_id))


def refresh(conn, account_id, today: date | None = None) -> dict:
    """Пересчёт для одного аккаунта по его режиму. Возвращает {mode, proposed, applied}."""
    st = one(conn, "SELECT mode FROM price_settings WHERE account_id = %s", (account_id,))
    mode = st["mode"] if st else "off"
    if mode == "off":
        return {"mode": mode, "proposed": 0, "applied": 0}
    items = compute(conn, account_id, today)
    run(conn, "DELETE FROM price_suggestions WHERE account_id = %s AND status = 'pending'", (account_id,))
    applied = 0
    if mode == "suggest":
        for s in items[:PREVIEW_LIMIT * 5]:
            run(conn, "INSERT INTO price_suggestions (account_id, room_type_id, date, current_price, suggested_price, base_price, reasons)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (account_id, s["room_type_id"], s["date"], s["current_price"], s["suggested_price"], s["base_price"], s["reasons"][:500]))
    else:
        for s in items:
            _apply_one(conn, account_id, s, "auto")
            applied += 1
        if applied:
            audit.record(conn, account_id, None, "autoprice", f"Автоцены изменили цены: {applied} дат(ы)")
            notify.send(conn, account_id, "automation", f"Автоцены: обновлено цен — {applied}. Подробности — в разделе «Цены → Автоцены», журнал изменений.",
                        link="#/rates", bell=True)
    run(conn, "UPDATE price_settings SET last_run_on = current_date WHERE account_id = %s", (account_id,))
    return {"mode": mode, "proposed": len(items) if mode == "suggest" else 0, "applied": applied}


def run_due() -> int:
    """Раз в день пересчитывает цены у аккаунтов с включёнными автоценами (вызывается планировщиком)."""
    with tx() as conn:
        ids = [r["account_id"] for r in all_(conn, "SELECT s.account_id FROM price_settings s JOIN accounts a ON a.id = s.account_id"
                                                   " WHERE s.mode <> 'off' AND a.status = 'active' AND 'autoprice' = ANY(a.modules)"
                                                   " AND (s.last_run_on IS NULL OR s.last_run_on < current_date)")]
    done = 0
    for aid in ids:
        try:
            with tx() as conn:
                refresh(conn, aid)
            done += 1
        except Exception:  # noqa: BLE001
            log.exception("Автоцены: сбой аккаунта %s", aid)
    return done
