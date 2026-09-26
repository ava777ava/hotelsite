"""Регистрация, вход, сотрудники, настройка объекта и номеров."""
from starlette.routing import Route

from ..auth import hash_password, make_token, new_ical_token, verify_password
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..expenses import create_default_categories
from ..util import opt_str, parse_int, parse_money, parse_uuid, req_str, slugify
from .base import Ctx, api

ROLE_LABELS = {"owner": "Владелец", "manager": "Администратор", "housekeeper": "Горничная"}


def _unique_slug(conn, base: str) -> str:
    slug, n = base, 1
    while one(conn, "SELECT 1 FROM properties WHERE public_slug = %s", (slug,)):
        n += 1
        slug = f"{base}-{n}"
    return slug


# ---------- авторизация ----------

@api(public=True)
def register(c: Ctx):
    account_name = req_str(c.data, "account_name", "Название компании или объекта", 200)
    name = req_str(c.data, "name", "Ваше имя", 200)
    email = req_str(c.data, "email", "Email", 200).lower()
    password = str(c.data.get("password") or "")
    if "@" not in email:
        raise ApiError(422, "Проверьте email", {"field": "email"})
    if len(password) < 8:
        raise ApiError(422, "Пароль должен быть не короче 8 символов", {"field": "password"})
    with tx() as conn:
        if one(conn, "SELECT 1 FROM users WHERE lower(email) = %s", (email,)):
            raise ApiError(409, "Пользователь с таким email уже зарегистрирован", {"field": "email"})
        acc = one(conn, "INSERT INTO accounts (name) VALUES (%s) RETURNING id", (account_name,))
        user = one(
            conn,
            "INSERT INTO users (account_id, email, password_hash, name, role)"
            " VALUES (%s, %s, %s, %s, 'owner') RETURNING id",
            (acc["id"], email, hash_password(password), name),
        )
        create_default_categories(conn, acc["id"])
    return {"token": make_token(user["id"], acc["id"], "owner")}


@api(public=True)
def login(c: Ctx):
    email = str(c.data.get("email") or "").strip().lower()
    password = str(c.data.get("password") or "")
    with tx() as conn:
        user = one(
            conn,
            "SELECT u.id, u.account_id, u.role, u.password_hash, a.status FROM users u"
            " JOIN accounts a ON a.id = u.account_id WHERE lower(u.email) = %s",
            (email,),
        )
    if not user or not verify_password(password, user["password_hash"]):
        raise ApiError(401, "Неверный email или пароль")
    if user["status"] != "active":
        raise ApiError(403, "Аккаунт приостановлен. Свяжитесь с поддержкой")
    return {"token": make_token(user["id"], user["account_id"], user["role"])}


@api()
def me(c: Ctx):
    with tx() as conn:
        user = one(
            conn,
            "SELECT u.id, u.name, u.email, u.role, a.name AS account_name, a.plan, a.status"
            " FROM users u JOIN accounts a ON a.id = u.account_id WHERE u.id = %s AND u.account_id = %s",
            (c.p.user_id, c.account_id),
        )
        if not user:
            raise ApiError(401, "Нужно войти в систему")
        props = all_(
            conn,
            "SELECT id, name, public_slug FROM properties WHERE account_id = %s ORDER BY created_at",
            (c.account_id,),
        )
    return {**user, "properties": props}


# ---------- сотрудники ----------

@api("owner")
def list_users(c: Ctx):
    with tx() as conn:
        return all_(
            conn,
            "SELECT id, name, email, role, created_at FROM users WHERE account_id = %s ORDER BY created_at",
            (c.account_id,),
        )


@api("owner")
def create_user(c: Ctx):
    name = req_str(c.data, "name", "Имя", 200)
    email = req_str(c.data, "email", "Email", 200).lower()
    role = c.data.get("role")
    if role not in ("manager", "housekeeper"):
        raise ApiError(422, "Роль: администратор или горничная")
    password = str(c.data.get("password") or "")
    if len(password) < 8:
        raise ApiError(422, "Пароль должен быть не короче 8 символов", {"field": "password"})
    with tx() as conn:
        if one(conn, "SELECT 1 FROM users WHERE lower(email) = %s", (email,)):
            raise ApiError(409, "Пользователь с таким email уже есть", {"field": "email"})
        return one(
            conn,
            "INSERT INTO users (account_id, email, password_hash, name, role)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id, name, email, role",
            (c.account_id, email, hash_password(password), name, role),
        )


@api("owner")
def delete_user(c: Ctx):
    uid = parse_uuid(c.path["id"])
    if uid == c.p.user_id:
        raise ApiError(422, "Нельзя удалить самого себя")
    with tx() as conn:
        n = run(conn, "DELETE FROM users WHERE id = %s AND account_id = %s AND role <> 'owner'",
                (uid, c.account_id))
    if not n:
        raise ApiError(404, "Сотрудник не найден")


# ---------- объект, категории, номера ----------

def _get_property(conn, account_id: str, property_id: str) -> dict:
    prop = one(conn, "SELECT * FROM properties WHERE id = %s AND account_id = %s",
               (parse_uuid(property_id, "Объект"), account_id))
    if not prop:
        raise ApiError(404, "Объект не найден")
    return prop


@api("owner")
def quick_setup(c: Ctx):
    """Мастер первого запуска: объект + категории + номера одним запросом."""
    name = req_str(c.data, "name", "Название объекта", 200)
    types = c.data.get("room_types") or []
    if not isinstance(types, list) or not types:
        raise ApiError(422, "Добавьте хотя бы одну категорию номеров")
    with tx() as conn:
        prop = one(
            conn,
            "INSERT INTO properties (account_id, name, address, phone, public_slug)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (c.account_id, name, opt_str(c.data, "address"), opt_str(c.data, "phone"),
             _unique_slug(conn, slugify(name))),
        )
        room_no = parse_int(c.data.get("first_number"), "Номер первой комнаты", 0, default=101)
        for i, t in enumerate(types):
            t_name = req_str(t, "name", "Название категории", 100)
            count = parse_int(t.get("count"), f"Количество номеров «{t_name}»", 1)
            if count > 200:
                raise ApiError(422, "Слишком много номеров в категории")
            rt = one(
                conn,
                "INSERT INTO room_types (account_id, property_id, name, capacity, base_price, sort_order, ical_token)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (c.account_id, prop["id"], t_name,
                 parse_int(t.get("capacity"), "Вместимость", 1, default=2),
                 parse_money(t.get("base_price"), "Цена"), i, new_ical_token()),
            )
            for _ in range(count):
                run(conn,
                    "INSERT INTO rooms (account_id, property_id, room_type_id, name, sort_order, ical_token)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (c.account_id, prop["id"], rt["id"], str(room_no), room_no, new_ical_token()))
                room_no += 1
    return prop


@api()
def get_property(c: Ctx):
    with tx() as conn:
        prop = _get_property(conn, c.account_id, c.path["id"])
        types = all_(conn, "SELECT id, property_id, name, description, capacity, base_price, min_stay, sort_order"
                           " FROM room_types WHERE property_id = %s ORDER BY sort_order, name", (prop["id"],))
        rooms = all_(conn, "SELECT id, room_type_id, name, sort_order FROM rooms"
                           " WHERE property_id = %s ORDER BY sort_order, name", (prop["id"],))
    for t in types:
        t["rooms"] = [r for r in rooms if r["room_type_id"] == t["id"]]
    prop["room_types"] = types
    return prop


@api("owner")
def update_property(c: Ctx):
    fields = {
        "name": lambda v: req_str({"v": v}, "v", "Название", 200),
        "address": lambda v: str(v or "")[:500],
        "phone": lambda v: str(v or "")[:50],
        "check_in_time": lambda v: str(v)[:5],
        "check_out_time": lambda v: str(v)[:5],
        "booking_enabled": bool,
        "timezone": lambda v: str(v)[:64],
    }
    sets, params = [], []
    for key, conv in fields.items():
        if key in c.data:
            sets.append(f"{key} = %s")
            params.append(conv(c.data[key]))
    if not sets:
        raise ApiError(422, "Нечего сохранять")
    with tx() as conn:
        prop = _get_property(conn, c.account_id, c.path["id"])
        return one(conn, f"UPDATE properties SET {', '.join(sets)} WHERE id = %s RETURNING *",
                   (*params, prop["id"]))


@api("owner")
def create_room_type(c: Ctx):
    with tx() as conn:
        prop = _get_property(conn, c.account_id, str(c.data.get("property_id")))
        return one(
            conn,
            "INSERT INTO room_types (account_id, property_id, name, description, capacity, base_price,"
            " min_stay, sort_order, ical_token) VALUES (%s, %s, %s, %s, %s, %s, %s,"
            " (SELECT coalesce(max(sort_order), 0) + 1 FROM room_types WHERE property_id = %s), %s)"
            " RETURNING id, property_id, name, description, capacity, base_price, min_stay, sort_order",
            (c.account_id, prop["id"], req_str(c.data, "name", "Название категории", 100),
             opt_str(c.data, "description"), parse_int(c.data.get("capacity"), "Вместимость", 1, default=2),
             parse_money(c.data.get("base_price"), "Цена"),
             parse_int(c.data.get("min_stay"), "Минимальный срок", 1, default=1), prop["id"], new_ical_token()),
        )


@api("owner")
def update_room_type(c: Ctx):
    rt_id = parse_uuid(c.path["id"])
    conv = {
        "name": lambda v: req_str({"v": v}, "v", "Название", 100),
        "description": lambda v: str(v or "")[:2000],
        "capacity": lambda v: parse_int(v, "Вместимость", 1),
        "base_price": lambda v: parse_money(v, "Цена"),
        "min_stay": lambda v: parse_int(v, "Минимальный срок", 1),
    }
    sets, params = [], []
    for key, f in conv.items():
        if key in c.data:
            sets.append(f"{key} = %s")
            params.append(f(c.data[key]))
    if not sets:
        raise ApiError(422, "Нечего сохранять")
    with tx() as conn:
        row = one(conn, f"UPDATE room_types SET {', '.join(sets)} WHERE id = %s AND account_id = %s"
                        " RETURNING id, property_id, name, description, capacity, base_price, min_stay, sort_order",
                  (*params, rt_id, c.account_id))
    if not row:
        raise ApiError(404, "Категория не найдена")
    return row


@api("owner")
def delete_room_type(c: Ctx):
    rt_id = parse_uuid(c.path["id"])
    with tx() as conn:
        if one(conn, "SELECT 1 FROM rooms WHERE room_type_id = %s", (rt_id,)):
            raise ApiError(409, "Сначала удалите или перенесите номера этой категории")
        if not run(conn, "DELETE FROM room_types WHERE id = %s AND account_id = %s", (rt_id, c.account_id)):
            raise ApiError(404, "Категория не найдена")


@api("owner")
def create_room(c: Ctx):
    rt_id = parse_uuid(c.data.get("room_type_id"), "Категория")
    with tx() as conn:
        rt = one(conn, "SELECT * FROM room_types WHERE id = %s AND account_id = %s", (rt_id, c.account_id))
        if not rt:
            raise ApiError(404, "Категория не найдена")
        name = req_str(c.data, "name", "Номер комнаты", 50)
        order = int(name) if name.isdigit() else 10000
        return one(
            conn,
            "INSERT INTO rooms (account_id, property_id, room_type_id, name, sort_order, ical_token)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, room_type_id, name, sort_order",
            (c.account_id, rt["property_id"], rt["id"], name, order, new_ical_token()),
        )


@api("owner")
def update_room(c: Ctx):
    room_id = parse_uuid(c.path["id"])
    with tx() as conn:
        room = one(conn, "SELECT * FROM rooms WHERE id = %s AND account_id = %s", (room_id, c.account_id))
        if not room:
            raise ApiError(404, "Номер не найден")
        name = req_str(c.data, "name", "Номер комнаты", 50) if "name" in c.data else room["name"]
        rt_id = room["room_type_id"]
        if "room_type_id" in c.data:
            rt = one(conn, "SELECT id FROM room_types WHERE id = %s AND account_id = %s AND property_id = %s",
                     (parse_uuid(c.data["room_type_id"]), c.account_id, room["property_id"]))
            if not rt:
                raise ApiError(404, "Категория не найдена")
            rt_id = rt["id"]
        return one(conn, "UPDATE rooms SET name = %s, room_type_id = %s WHERE id = %s"
                         " RETURNING id, room_type_id, name, sort_order", (name, rt_id, room_id))


@api("owner")
def delete_room(c: Ctx):
    room_id = parse_uuid(c.path["id"])
    with tx() as conn:
        if one(conn, "SELECT 1 FROM bookings WHERE room_id = %s AND status <> 'cancelled'"
                     " AND check_out >= current_date", (room_id,)):
            raise ApiError(409, "У номера есть действующие брони — сначала перенесите или отмените их")
        if not run(conn, "DELETE FROM rooms WHERE id = %s AND account_id = %s", (room_id, c.account_id)):
            raise ApiError(404, "Номер не найден")


routes = [
    Route("/api/auth/register", register, methods=["POST"]),
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/me", me),
    Route("/api/users", list_users),
    Route("/api/users", create_user, methods=["POST"]),
    Route("/api/users/{id}", delete_user, methods=["DELETE"]),
    Route("/api/setup", quick_setup, methods=["POST"]),
    Route("/api/properties/{id}", get_property),
    Route("/api/properties/{id}", update_property, methods=["PATCH"]),
    Route("/api/room-types", create_room_type, methods=["POST"]),
    Route("/api/room-types/{id}", update_room_type, methods=["PATCH"]),
    Route("/api/room-types/{id}", delete_room_type, methods=["DELETE"]),
    Route("/api/rooms", create_room, methods=["POST"]),
    Route("/api/rooms/{id}", update_room, methods=["PATCH"]),
    Route("/api/rooms/{id}", delete_room, methods=["DELETE"]),
]
