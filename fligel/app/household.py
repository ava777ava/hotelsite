"""Хозяйство: движение расходников по складу (приход, расход, списание по нормам при уборке) и «заканчивается»."""
from decimal import Decimal

from . import notify
from .db import all_, one, run
from .errors import ApiError

KINDS = {"in": "Приход", "out": "Расход", "writeoff": "Списание", "cleaning": "Списано при уборке", "correction": "Инвентаризация"}


def _fmt(v) -> str:
    """12.00 → «12», 2.50 → «2,5» — без лишних нулей, с десятичной запятой."""
    s = f"{Decimal(v):f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def move(conn, account_id, item_id, delta: Decimal, kind: str, note: str = "", user_id=None, room_id=None, clamp: bool = False) -> dict | None:
    """Меняет остаток и пишет движение. clamp=True (автосписание при уборке): если не хватает — списываем сколько есть, без ошибки."""
    item = one(conn, "SELECT * FROM stock_items WHERE id = %s AND account_id = %s FOR UPDATE", (item_id, account_id))
    if not item or item["archived"]:
        raise ApiError(404, "Позиция на складе не найдена")
    qty = Decimal(item["quantity"])
    delta = Decimal(delta)
    if qty + delta < 0:
        if not clamp:
            raise ApiError(422, f"На складе только {_fmt(qty)} {item['unit']} — больше списать нельзя", {"field": "amount"})
        delta = -qty
    if delta == 0:
        return None
    new_qty = qty + delta
    run(conn, "UPDATE stock_items SET quantity = %s WHERE id = %s", (new_qty, item["id"]))
    run(conn, "INSERT INTO stock_moves (account_id, item_id, delta, kind, note, room_id, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (account_id, item["id"], delta, kind, note[:300], room_id, user_id))
    _check_low(conn, {**item, "quantity": new_qty})
    return {"id": item["id"], "quantity": new_qty, "delta": delta}


def _check_low(conn, item: dict) -> None:
    """«Заканчивается»: остаток дошёл до минимума — одно сообщение в день на позицию; поднялся выше — сбрасываем."""
    qty, mn = Decimal(item["quantity"]), Decimal(item["min_quantity"])
    if mn > 0 and qty <= mn:
        if item["low_notified_on"] is None or item["low_notified_on"] < one(conn, "SELECT current_date AS d")["d"]:
            run(conn, "UPDATE stock_items SET low_notified_on = current_date WHERE id = %s", (item["id"],))
            notify.send(conn, item["account_id"], "stock", f"Заканчивается: {item['name']} — осталось {_fmt(qty)} {item['unit']} (минимум {_fmt(mn)}). Пора докупить.",
                        link="#/household", bell=True)
    elif item["low_notified_on"] is not None and qty > mn:
        run(conn, "UPDATE stock_items SET low_notified_on = NULL WHERE id = %s", (item["id"],))


def writeoff_for_cleaning(conn, account_id, room_id, user_id=None) -> int:
    """После уборки номера списывает расходники по нормам (мыло, шампунь, пакеты…). Возвращает число затронутых позиций."""
    room = one(conn, "SELECT id, property_id, name FROM rooms WHERE id = %s AND account_id = %s", (room_id, account_id))
    if not room:
        return 0
    n = 0
    for it in all_(conn, "SELECT id FROM stock_items WHERE account_id = %s AND property_id = %s AND NOT archived AND norm_per_cleaning > 0",
                   (account_id, room["property_id"])):
        item = one(conn, "SELECT norm_per_cleaning FROM stock_items WHERE id = %s", (it["id"],))
        if move(conn, account_id, it["id"], -Decimal(item["norm_per_cleaning"]), "cleaning", f"Уборка номера {room['name']}", user_id, room["id"], clamp=True):
            n += 1
    return n
