"""Уборка: статусы номеров, экран горничной, назначение, заметки к номерам."""
from starlette.routing import Route

from .. import audit, notify
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_uuid
from .base import Ctx, api
from .common import selected_property

STATUSES = ("clean", "dirty", "cleaning", "inspect", "repair")
LABELS = {"clean": "Чистый", "dirty": "Нужна уборка", "cleaning": "Убирают", "inspect": "Ждёт проверки",
          "repair": "Ремонт", "occupied": "Заселён"}

# Фактический статус: явно выставленный, а если номер «чистый», но после последней отметки об уборке
# из него выезжали (за последнюю неделю) — он грязный. Проживающий гость → «Заселён».
EFFECTIVE_SQL = """(CASE
    WHEN r.hk_status <> 'clean' THEN r.hk_status
    WHEN EXISTS (SELECT 1 FROM bookings b WHERE b.room_id = r.id AND b.status IN ('confirmed', 'pending')
                 AND b.check_out <= current_date AND b.check_out >= current_date - 7
                 AND (r.cleaned_on IS NULL OR b.check_out > r.cleaned_on)) THEN 'dirty'
    WHEN EXISTS (SELECT 1 FROM bookings b WHERE b.room_id = r.id AND b.status IN ('confirmed', 'pending')
                 AND b.check_in < current_date AND b.check_out > current_date) THEN 'occupied'
    ELSE 'clean' END)"""


@api()
def housekeeping_list(c: Ctx):
    """Все номера объекта со статусом уборки — для экрана горничной и администратора."""
    with tx() as conn:
        prop = selected_property(conn, c.account_id, c.q.get("property_id"))
        rooms = all_(conn, f"""
            SELECT r.id, r.name, rt.name AS type, {EFFECTIVE_SQL} AS status, r.hk_note, r.note, r.hk_updated_at,
                   CASE WHEN r.hk_assigned_on = current_date THEN r.hk_assigned_to END AS assigned_to,
                   CASE WHEN r.hk_assigned_on = current_date THEN u.name END AS assigned_name,
                   (SELECT b.guest_name FROM bookings b WHERE b.room_id = r.id AND b.status IN ('confirmed', 'pending')
                      AND b.check_out = current_date ORDER BY b.check_in LIMIT 1) AS departing,
                   EXISTS (SELECT 1 FROM bookings b WHERE b.room_id = r.id AND b.status IN ('confirmed', 'pending')
                      AND b.check_out = current_date) AS departs_today,
                   EXISTS (SELECT 1 FROM bookings b WHERE b.room_id = r.id AND b.status IN ('confirmed', 'pending')
                      AND b.check_in = current_date) AS arrives_today,
                   (SELECT min(b.check_in) FROM bookings b WHERE b.room_id = r.id AND b.status IN ('confirmed', 'pending')
                      AND b.check_in >= current_date) AS next_arrival
            FROM rooms r JOIN room_types rt ON rt.id = r.room_type_id LEFT JOIN users u ON u.id = r.hk_assigned_to
            WHERE r.property_id = %s AND r.account_id = %s ORDER BY rt.sort_order, r.sort_order, r.name""",
                     (prop["id"], c.account_id))
        staff = all_(conn, "SELECT id, name FROM users WHERE account_id = %s AND role = 'housekeeper' ORDER BY name", (c.account_id,))
    counts = {}
    for r in rooms:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"rooms": rooms, "housekeepers": staff, "counts": counts, "labels": LABELS, "me": c.p.user_id}


@api()
def set_status(c: Ctx):
    """Сменить статус номера. Горничной доступны все статусы (убрала, начала, нужна проверка, поломка)."""
    status = c.data.get("status")
    if status not in STATUSES:
        raise ApiError(422, "Неверный статус номера")
    note = opt_str(c.data, "note", max_len=300)
    if status == "repair" and not note:
        raise ApiError(422, "Опишите, что случилось, — администратор увидит это сразу", {"field": "note"})
    rid = parse_uuid(c.path["id"], "Номер")
    report = None
    with tx() as conn:
        room = one(conn, "SELECT r.id, r.name, r.hk_status FROM rooms r WHERE r.id = %s AND r.account_id = %s", (rid, c.account_id))
        if not room:
            raise ApiError(404, "Номер не найден")
        run(conn, "UPDATE rooms SET hk_status = %s, hk_note = %s, hk_updated_at = now(),"
                  " cleaned_on = CASE WHEN %s = 'clean' THEN current_date ELSE cleaned_on END,"
                  " hk_assigned_on = CASE WHEN %s = 'clean' THEN NULL ELSE hk_assigned_on END WHERE id = %s",
            (status, note if status == "repair" else "", status, status, rid))
        run(conn, "INSERT INTO room_status_log (account_id, room_id, user_id, status, note) VALUES (%s, %s, %s, %s, %s)",
            (c.account_id, rid, c.p.user_id, status, note))
        if status == "repair" and room["hk_status"] != "repair":
            text = f"Номер {room['name']}: поломка — {note}"
            audit.record(conn, c.account_id, c.p.user_id, "room_repair", text, "room", rid)
            notify.send(conn, c.account_id, "room_issue", text, link="#/cleaning", bell=True)
        return {"id": rid, "status": status, "note": note if status == "repair" else ""}


@api("manager")
def assign(c: Ctx):
    """Назначить уборку горничной на сегодня (user_id = null — снять назначение)."""
    ids = c.data.get("room_ids")
    if not isinstance(ids, list) or not ids:
        raise ApiError(422, "Выберите номера")
    ids = [parse_uuid(i, "Номер") for i in ids][:200]
    uid = parse_uuid(c.data["user_id"], "Сотрудник") if c.data.get("user_id") else None
    with tx() as conn:
        if uid and not one(conn, "SELECT 1 FROM users WHERE id = %s AND account_id = %s", (uid, c.account_id)):
            raise ApiError(404, "Сотрудник не найден")
        n = run(conn, "UPDATE rooms SET hk_assigned_to = %s, hk_assigned_on = CASE WHEN %s::uuid IS NULL THEN NULL ELSE current_date END"
                      " WHERE account_id = %s AND id = ANY(%s::uuid[])", (uid, uid, c.account_id, ids))
    return {"updated": n}


@api("manager")
def set_room_note(c: Ctx):
    note = opt_str(c.data, "note", max_len=500)
    with tx() as conn:
        if not run(conn, "UPDATE rooms SET note = %s WHERE id = %s AND account_id = %s", (note, parse_uuid(c.path["id"], "Номер"), c.account_id)):
            raise ApiError(404, "Номер не найден")
    return {"note": note}


routes = [
    Route("/api/housekeeping", housekeeping_list),
    Route("/api/rooms/{id}/status", set_status, methods=["POST"]),
    Route("/api/rooms/{id}/note", set_room_note, methods=["PUT"]),
    Route("/api/housekeeping/assign", assign, methods=["POST"]),
]
