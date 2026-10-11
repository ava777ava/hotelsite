"""Хозяйство: склад расходников, счётчики (с автоматическим расходом в «Финансах»), инвентарь номеров и проверка после выезда."""
from datetime import date
from decimal import Decimal

from starlette.routing import Route

from .. import audit, household, notify
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_date, parse_int, parse_money, parse_uuid, req_str
from .base import Ctx, api
from .common import selected_property
from .tasks import create_task

METER_KINDS = {"water_cold": ("Холодная вода", "м³"), "water_hot": ("Горячая вода", "м³"), "electricity": ("Электричество", "кВт·ч"),
               "gas": ("Газ", "м³"), "heat": ("Тепло", "Гкал")}
UTILITY_CATEGORY = "коммунальные услуги"


def _qty(data: dict, key: str, label: str) -> Decimal:
    return parse_money(data.get(key), label)


# ---------- склад ----------

def _items(conn, account_id, property_id) -> list[dict]:
    return all_(conn, "SELECT id, name, unit, quantity, min_quantity, norm_per_cleaning, (min_quantity > 0 AND quantity <= min_quantity) AS low"
                      " FROM stock_items WHERE account_id = %s AND property_id = %s AND NOT archived ORDER BY low DESC, name",
                (account_id, property_id))


@api()
def stock_list(c: Ctx):
    """Склад объекта. Горничная видит остатки и может отметить расход; приход и настройки — у администратора."""
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.q.get("property_id"))
        moves = all_(conn, "SELECT m.id, m.delta, m.kind, m.note, m.created_at, i.name AS item_name, i.unit, coalesce(u.name, '') AS user_name FROM stock_moves m"
                           " JOIN stock_items i ON i.id = m.item_id LEFT JOIN users u ON u.id = m.user_id WHERE i.property_id = %s AND m.account_id = %s"
                           " ORDER BY m.created_at DESC LIMIT 30", (prop["id"], c.account_id))
        return {"property_id": prop["id"], "items": _items(conn, c.account_id, prop["id"]), "moves": moves, "kinds": household.KINDS,
                "can_edit": c.p.role in ("owner", "manager")}


def _stock_fields(data: dict, current: dict | None) -> dict:
    out: dict = {}
    if current is None or "name" in data:
        out["name"] = req_str(data, "name", "Название", 120)
    if current is None or "unit" in data:
        out["unit"] = opt_str(data, "unit", "шт", 20) or "шт"
    if current is None or "min_quantity" in data:
        out["min_quantity"] = _qty(data, "min_quantity", "Минимальный остаток")
    if current is None or "norm_per_cleaning" in data:
        out["norm_per_cleaning"] = _qty(data, "norm_per_cleaning", "Норма на уборку")
    return out


@api("manager")
def stock_create(c: Ctx):
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.data.get("property_id"))
        f = _stock_fields(c.data, None)
        start = _qty(c.data, "quantity", "Остаток")
        row = one(conn, f"INSERT INTO stock_items (account_id, property_id, quantity, {', '.join(f)}) VALUES (%s, %s, 0, {', '.join(['%s'] * len(f))}) RETURNING id",
                  (c.account_id, prop["id"], *f.values()))
        if start > 0:
            household.move(conn, c.account_id, row["id"], start, "in", "Начальный остаток", c.p.user_id)
        return one(conn, "SELECT id, name, unit, quantity, min_quantity, norm_per_cleaning FROM stock_items WHERE id = %s", (row["id"],))


@api("manager")
def stock_update(c: Ctx):
    iid = parse_uuid(c.path["id"], "Позиция")
    with tx() as conn:
        cur = one(conn, "SELECT * FROM stock_items WHERE id = %s AND account_id = %s FOR UPDATE", (iid, c.account_id))
        if not cur:
            raise ApiError(404, "Позиция не найдена")
        f = _stock_fields(c.data, cur)
        if "archived" in c.data:
            f["archived"] = bool(c.data["archived"])
        if f:
            run(conn, f"UPDATE stock_items SET {', '.join(f'{k} = %s' for k in f)} WHERE id = %s", (*f.values(), iid))
        return one(conn, "SELECT id, name, unit, quantity, min_quantity, norm_per_cleaning, archived FROM stock_items WHERE id = %s", (iid,))


@api()
def stock_move(c: Ctx):
    """kind: in — приход, out — расход (может горничная), writeoff — списание (брак, потеря), correction — «на складе на самом деле N»."""
    kind = c.data.get("kind")
    if kind not in ("in", "out", "writeoff", "correction"):
        raise ApiError(422, "Неизвестная операция")
    if kind != "out" and c.p.role not in ("owner", "manager"):
        raise ApiError(403, "Недостаточно прав: приход и списание — у администратора")
    note = opt_str(c.data, "note", max_len=300)
    with tx() as conn:
        item = one(conn, "SELECT id, quantity FROM stock_items WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Позиция"), c.account_id))
        if not item:
            raise ApiError(404, "Позиция не найдена")
        if kind == "correction":
            delta = _qty(c.data, "amount", "Фактический остаток") - Decimal(item["quantity"])
            if delta == 0:
                return {"quantity": item["quantity"], "delta": 0}
        else:
            amount = _qty(c.data, "amount", "Количество")
            if amount <= 0:
                raise ApiError(422, "Введите количество больше нуля", {"field": "amount"})
            delta = amount if kind == "in" else -amount
        res = household.move(conn, c.account_id, item["id"], delta, kind, note, c.p.user_id)
        return {"quantity": res["quantity"], "delta": res["delta"]}


@api("manager")
def stock_history(c: Ctx):
    with tx() as conn:
        item = one(conn, "SELECT id, name, unit FROM stock_items WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Позиция"), c.account_id))
        if not item:
            raise ApiError(404, "Позиция не найдена")
        moves = all_(conn, "SELECT m.delta, m.kind, m.note, m.created_at, coalesce(u.name, '') AS user_name FROM stock_moves m LEFT JOIN users u ON u.id = m.user_id"
                           " WHERE m.item_id = %s ORDER BY m.created_at DESC LIMIT 100", (item["id"],))
    return {"item": item, "moves": moves}


# ---------- счётчики ----------

def _utility_category(conn, account_id):
    cat = one(conn, "SELECT id FROM expense_categories WHERE account_id = %s AND NOT archived AND lower(name) = %s", (account_id, UTILITY_CATEGORY))
    return cat or one(conn, "SELECT id FROM expense_categories WHERE account_id = %s AND NOT archived ORDER BY sort_order LIMIT 1", (account_id,))


def _meter_row(conn, account_id, mid) -> dict:
    m = one(conn, "SELECT m.*, r.name AS room_name FROM meters m LEFT JOIN rooms r ON r.id = m.room_id WHERE m.id = %s AND m.account_id = %s",
            (parse_uuid(mid, "Счётчик"), account_id))
    if not m:
        raise ApiError(404, "Счётчик не найден")
    return m


@api("manager")
def meters_list(c: Ctx):
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.q.get("property_id"))
        meters = all_(conn, "SELECT m.id, m.kind, m.name, m.unit, m.tariff, m.room_id, r.name AS room_name FROM meters m LEFT JOIN rooms r ON r.id = m.room_id"
                            " WHERE m.account_id = %s AND m.property_id = %s AND NOT m.archived ORDER BY m.kind, r.name NULLS FIRST, m.name", (c.account_id, prop["id"]))
        for m in meters:
            last = all_(conn, "SELECT date, value, consumption, cost FROM meter_readings WHERE meter_id = %s ORDER BY date DESC, created_at DESC LIMIT 2", (m["id"],))
            m["last"] = last[0] if last else None
            m["label"] = METER_KINDS[m["kind"]][0] + (f" · {m['name']}" if m["name"] else "")
            m["monthly"] = all_(conn, "SELECT date_trunc('month', date)::date AS month, sum(consumption) AS consumption, sum(cost) AS cost FROM meter_readings"
                                      " WHERE meter_id = %s AND date >= current_date - interval '6 months' GROUP BY 1 ORDER BY 1", (m["id"],))
        rooms = all_(conn, "SELECT id, name FROM rooms WHERE property_id = %s ORDER BY sort_order, name", (prop["id"],))
    return {"property_id": prop["id"], "meters": meters, "rooms": rooms, "kinds": {k: {"label": v[0], "unit": v[1]} for k, v in METER_KINDS.items()}}


@api("manager")
def meter_create(c: Ctx):
    kind = c.data.get("kind")
    if kind not in METER_KINDS:
        raise ApiError(422, "Выберите тип счётчика")
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.data.get("property_id"))
        room_id = None
        if c.data.get("room_id"):
            room_id = parse_uuid(c.data["room_id"], "Номер")
            if not one(conn, "SELECT 1 FROM rooms WHERE id = %s AND account_id = %s AND property_id = %s", (room_id, c.account_id, prop["id"])):
                raise ApiError(404, "Номер не найден")
        row = one(conn, "INSERT INTO meters (account_id, property_id, room_id, kind, name, unit, tariff) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                  (c.account_id, prop["id"], room_id, kind, opt_str(c.data, "name", max_len=80), METER_KINDS[kind][1], parse_money(c.data.get("tariff"), "Тариф")))
        return {"id": row["id"]}


@api("manager")
def meter_update(c: Ctx):
    with tx() as conn:
        m = _meter_row(conn, c.account_id, c.path["id"])
        sets, params = [], []
        if "name" in c.data:
            sets.append("name = %s"); params.append(opt_str(c.data, "name", max_len=80))
        if "tariff" in c.data:
            sets.append("tariff = %s"); params.append(parse_money(c.data["tariff"], "Тариф"))
        if "archived" in c.data:
            sets.append("archived = %s"); params.append(bool(c.data["archived"]))
        if sets:
            run(conn, f"UPDATE meters SET {', '.join(sets)} WHERE id = %s", (*params, m["id"]))
    return {"ok": True}


@api("manager")
def readings_list(c: Ctx):
    with tx() as conn:
        m = _meter_row(conn, c.account_id, c.path["id"])
        rows = all_(conn, "SELECT x.id, x.date, x.value, x.consumption, x.tariff, x.cost, x.replaced, x.note, x.expense_id, coalesce(u.name, '') AS user_name"
                          " FROM meter_readings x LEFT JOIN users u ON u.id = x.user_id WHERE x.meter_id = %s ORDER BY x.date DESC, x.created_at DESC LIMIT 60", (m["id"],))
    return {"meter": {"id": m["id"], "unit": m["unit"], "tariff": m["tariff"], "kind": m["kind"]}, "readings": rows}


@api("manager")
def reading_create(c: Ctx):
    """Новое показание: считаем расход с предыдущего, стоимость по тарифу и сразу заносим расход в «Финансы»."""
    day = parse_date(c.data["date"], "Дата", "date") if c.data.get("date") else date.today()
    value = parse_money(c.data.get("value"), "Показание")
    replaced = bool(c.data.get("replaced"))
    with tx() as conn:
        m = _meter_row(conn, c.account_id, c.path["id"])
        conn.execute("SELECT 1 FROM meters WHERE id = %s FOR UPDATE", (m["id"],))
        prev = one(conn, "SELECT date, value FROM meter_readings WHERE meter_id = %s ORDER BY date DESC, created_at DESC LIMIT 1", (m["id"],))
        consumption = Decimal("0")
        if prev:
            if day < prev["date"]:
                raise ApiError(422, f"Дата раньше предыдущего показания ({prev['date'].strftime('%d.%m.%Y')})", {"field": "date"})
            if not replaced:
                if value < Decimal(prev["value"]):
                    raise ApiError(422, f"Показание меньше предыдущего ({prev['value']}). Если счётчик заменили, отметьте «счётчик заменён»", {"field": "value"})
                consumption = value - Decimal(prev["value"])
        tariff = Decimal(m["tariff"])
        cost = (consumption * tariff).quantize(Decimal("0.01"))
        expense_id = None
        if cost > 0:
            cat = _utility_category(conn, c.account_id)
            if cat:
                label = METER_KINDS[m["kind"]][0].lower()
                where = f"номер {m['room_name']}" if m["room_name"] else "общий"
                comment = f"Счётчик ({label}, {where}): {household._fmt(consumption)} {m['unit']} × {household._fmt(tariff)} ₽ — показания {household._fmt(prev['value'])} → {household._fmt(value)}"
                exp = one(conn, "INSERT INTO expenses (account_id, property_id, room_id, category_id, date, amount, comment, created_by)"
                                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                          (c.account_id, m["property_id"], m["room_id"], cat["id"], day, cost, comment[:1000], c.p.user_id))
                expense_id = exp["id"]
        row = one(conn, "INSERT INTO meter_readings (account_id, meter_id, date, value, consumption, tariff, cost, expense_id, replaced, note, user_id)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, date, value, consumption, tariff, cost, expense_id",
                  (c.account_id, m["id"], day, value, consumption, tariff, cost, expense_id, replaced, opt_str(c.data, "note", max_len=200), c.p.user_id))
        return row


@api("manager")
def reading_delete(c: Ctx):
    """Удалить можно только последнее показание счётчика (иначе цепочка расходов собьётся); расход, созданный им, удаляется тоже."""
    with tx() as conn:
        r = one(conn, "SELECT x.* FROM meter_readings x WHERE x.id = %s AND x.account_id = %s FOR UPDATE", (parse_uuid(c.path["id"], "Показание"), c.account_id))
        if not r:
            raise ApiError(404, "Показание не найдено")
        last = one(conn, "SELECT id FROM meter_readings WHERE meter_id = %s ORDER BY date DESC, created_at DESC LIMIT 1", (r["meter_id"],))
        if last["id"] != r["id"]:
            raise ApiError(422, "Удалить можно только последнее показание счётчика")
        run(conn, "DELETE FROM meter_readings WHERE id = %s", (r["id"],))
        if r["expense_id"]:
            run(conn, "DELETE FROM expenses WHERE id = %s AND account_id = %s", (r["expense_id"], c.account_id))
    return {"ok": True}


# ---------- инвентарь номеров и проверка после выезда ----------

def _room(conn, account_id, rid) -> dict:
    room = one(conn, "SELECT id, name, property_id, room_type_id FROM rooms WHERE id = %s AND account_id = %s", (parse_uuid(rid, "Номер"), account_id))
    if not room:
        raise ApiError(404, "Номер не найден")
    return room


@api()
def inventory_get(c: Ctx):
    with tx() as conn:
        room = _room(conn, c.account_id, c.path["id"])
        items = all_(conn, "SELECT id, name, qty, note FROM inventory_items WHERE room_id = %s ORDER BY sort_order, created_at", (room["id"],))
        last = one(conn, "SELECT k.id, k.created_at, k.problems, coalesce(u.name, '') AS user_name FROM inventory_checks k LEFT JOIN users u ON u.id = k.user_id"
                         " WHERE k.room_id = %s ORDER BY k.created_at DESC LIMIT 1", (room["id"],))
    return {"room": {"id": room["id"], "name": room["name"]}, "items": items, "last_check": last}


@api("manager")
def inventory_add(c: Ctx):
    with tx() as conn:
        room = _room(conn, c.account_id, c.path["id"])
        n = one(conn, "SELECT count(*) AS n FROM inventory_items WHERE room_id = %s", (room["id"],))["n"]
        if n >= 200:
            raise ApiError(422, "Слишком много позиций в номере (максимум 200)")
        return one(conn, "INSERT INTO inventory_items (account_id, room_id, name, qty, note, sort_order) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, name, qty, note",
                   (c.account_id, room["id"], req_str(c.data, "name", "Название", 120), max(parse_int(c.data.get("qty"), "Количество", 1, default=1), 1),
                    opt_str(c.data, "note", max_len=200), n))


@api("manager")
def inventory_update(c: Ctx):
    with tx() as conn:
        it = one(conn, "SELECT * FROM inventory_items WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Позиция"), c.account_id))
        if not it:
            raise ApiError(404, "Позиция не найдена")
        name = req_str(c.data, "name", "Название", 120) if "name" in c.data else it["name"]
        qty = max(parse_int(c.data["qty"], "Количество", 1), 1) if "qty" in c.data else it["qty"]
        note = opt_str(c.data, "note", max_len=200) if "note" in c.data else it["note"]
        return one(conn, "UPDATE inventory_items SET name = %s, qty = %s, note = %s WHERE id = %s RETURNING id, name, qty, note", (name, qty, note, it["id"]))


@api("manager")
def inventory_delete(c: Ctx):
    with tx() as conn:
        if not run(conn, "DELETE FROM inventory_items WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Позиция"), c.account_id)):
            raise ApiError(404, "Позиция не найдена")
    return {"ok": True}


@api("manager")
def inventory_copy(c: Ctx):
    """Скопировать список этого номера в другие номера той же категории (позиции с такими же названиями не дублируются)."""
    with tx() as conn:
        room = _room(conn, c.account_id, c.path["id"])
        targets = all_(conn, "SELECT id FROM rooms WHERE account_id = %s AND room_type_id = %s AND id <> %s", (c.account_id, room["room_type_id"], room["id"]))
        src = all_(conn, "SELECT name, qty, note, sort_order FROM inventory_items WHERE room_id = %s", (room["id"],))
        added = 0
        for t in targets:
            have = {r["name"].lower() for r in all_(conn, "SELECT name FROM inventory_items WHERE room_id = %s", (t["id"],))}
            for it in src:
                if it["name"].lower() not in have:
                    run(conn, "INSERT INTO inventory_items (account_id, room_id, name, qty, note, sort_order) VALUES (%s, %s, %s, %s, %s, %s)",
                        (c.account_id, t["id"], it["name"], it["qty"], it["note"], it["sort_order"]))
                    added += 1
    return {"rooms": len(targets), "added": added}


@api()
def inventory_check(c: Ctx):
    """Проверка номера после выезда (горничная): по каждой позиции — на месте / нет / сломано. Проблемы → задача администратору и колокольчик."""
    rows = c.data.get("items")
    if not isinstance(rows, list) or not rows:
        raise ApiError(422, "Отметьте позиции списка")
    with tx() as conn:
        room = _room(conn, c.account_id, c.path["id"])
        inv = {str(i["id"]): i for i in all_(conn, "SELECT id, name, qty FROM inventory_items WHERE room_id = %s", (room["id"],))}
        booking_id = None
        if c.data.get("booking_id"):
            booking_id = parse_uuid(c.data["booking_id"], "Бронь")
            if not one(conn, "SELECT 1 FROM bookings WHERE id = %s AND account_id = %s AND room_id = %s", (booking_id, c.account_id, room["id"])):
                booking_id = None
        chk = one(conn, "INSERT INTO inventory_checks (account_id, room_id, booking_id, user_id) VALUES (%s, %s, %s, %s) RETURNING id", (c.account_id, room["id"], booking_id, c.p.user_id))
        problems = []
        for r in rows[:300]:
            it = inv.get(str(r.get("item_id")))
            state = r.get("state")
            if not it or state not in ("ok", "missing", "broken"):
                continue
            note = opt_str(r, "note", max_len=200)
            run(conn, "INSERT INTO inventory_check_items (check_id, name, qty, state, note) VALUES (%s, %s, %s, %s, %s)", (chk["id"], it["name"], it["qty"], state, note))
            if state != "ok":
                problems.append((it["name"], state, note))
        run(conn, "UPDATE inventory_checks SET problems = %s WHERE id = %s", (len(problems), chk["id"]))
        for name, state, note in problems:
            title = f"Номер {room['name']}: {'не хватает' if state == 'missing' else 'сломано'} — {name}"
            if not one(conn, "SELECT 1 FROM tasks WHERE account_id = %s AND title = %s AND done_at IS NULL", (c.account_id, title)):
                create_task(conn, c.account_id, title, description=note, due_date=date.today(), room_id=room["id"], booking_id=booking_id, source="inventory", created_by=c.p.user_id)
        if problems:
            text = f"Номер {room['name']}: после выезда не в порядке — " + ", ".join(f"{n} ({'нет' if s == 'missing' else 'сломано'})" for n, s, _ in problems[:6])
            audit.record(conn, c.account_id, c.p.user_id, "inventory_problem", text, "room", room["id"])
            notify.send(conn, c.account_id, "room_issue", text, link="#/tasks", bell=True)
    return {"id": chk["id"], "problems": len(problems)}


@api("manager")
def inventory_checks(c: Ctx):
    with tx() as conn:
        room = _room(conn, c.account_id, c.path["id"])
        checks = all_(conn, "SELECT k.id, k.created_at, k.problems, coalesce(u.name, '') AS user_name FROM inventory_checks k LEFT JOIN users u ON u.id = k.user_id"
                            " WHERE k.room_id = %s ORDER BY k.created_at DESC LIMIT 20", (room["id"],))
        for k in checks:
            k["items"] = all_(conn, "SELECT name, qty, state, note FROM inventory_check_items WHERE check_id = %s AND state <> 'ok'", (k["id"],))
    return {"checks": checks}


routes = [
    Route("/api/stock", stock_list),
    Route("/api/stock/items", stock_create, methods=["POST"]),
    Route("/api/stock/items/{id}", stock_update, methods=["PATCH"]),
    Route("/api/stock/items/{id}/move", stock_move, methods=["POST"]),
    Route("/api/stock/items/{id}/history", stock_history),
    Route("/api/meters", meters_list),
    Route("/api/meters", meter_create, methods=["POST"]),
    Route("/api/meters/{id}", meter_update, methods=["PATCH"]),
    Route("/api/meters/{id}/readings", readings_list),
    Route("/api/meters/{id}/readings", reading_create, methods=["POST"]),
    Route("/api/meter-readings/{id}", reading_delete, methods=["DELETE"]),
    Route("/api/rooms/{id}/inventory", inventory_get),
    Route("/api/rooms/{id}/inventory", inventory_add, methods=["POST"]),
    Route("/api/rooms/{id}/inventory/copy", inventory_copy, methods=["POST"]),
    Route("/api/rooms/{id}/inventory-check", inventory_check, methods=["POST"]),
    Route("/api/rooms/{id}/inventory-checks", inventory_checks),
    Route("/api/inventory/{id}", inventory_update, methods=["PATCH"]),
    Route("/api/inventory/{id}", inventory_delete, methods=["DELETE"]),
]
