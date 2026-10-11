"""Гости: список и карточка по телефону, теги, заметки, чёрный список, шаблоны сообщений."""
import re
from datetime import date
from decimal import Decimal

from starlette.routing import Route

from .. import booklog, config, mail
from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import opt_str, parse_date, parse_int, parse_uuid, req_str
from .base import Ctx, api

# SQL-выражение «ключ гостя»: последние 10 цифр телефона (+7 900…, 8 900… и 900… — один гость)
KEY_SQL = "right(regexp_replace({col}, '\\D', '', 'g'), 10)"
BK_KEY = KEY_SQL.format(col="b.guest_phone")

DEFAULT_TEMPLATES = [
    ("Подтверждение бронирования",
     "Здравствуйте, {имя}! Ваше бронирование подтверждено.\n{объект}, номер {номер}\nЗаезд: {заезд} с {время заезда}, выезд: {выезд} до {время выезда}.\n"
     "Ночей: {ночей}. Стоимость: {сумма}. К оплате: {сумма к оплате}.\nАдрес: {адрес}. Телефон: {телефон объекта}.\nЖдём вас!"),
    ("Напоминание о заезде",
     "Здравствуйте, {имя}! Напоминаем: ждём вас {заезд} с {время заезда} — {объект}, {адрес}. Если планы изменились, сообщите, пожалуйста: {телефон объекта}."),
    ("Просьба об оплате",
     "Здравствуйте, {имя}! Чтобы закрепить бронь на {даты}, пожалуйста, внесите оплату: {сумма к оплате}. Реквизиты вышлем по запросу. {объект}."),
    ("Как заселиться",
     "Здравствуйте, {имя}! Заселение {заезд} с {время заезда}. Адрес: {адрес}. По приезду позвоните: {телефон объекта} — мы вас встретим. Номер: {номер}."),
    ("Спасибо за визит",
     "{имя}, спасибо, что остановились у нас ({объект})! Будем рады видеть вас снова. Если захотите вернуться — звоните: {телефон объекта}."),
]
PLACEHOLDERS = ["имя", "даты", "заезд", "выезд", "ночей", "срок", "номер", "объект", "адрес", "телефон объекта",
                "время заезда", "время выезда", "сумма", "сумма к оплате", "код двери", "ссылка на анкету", "ссылка на отзыв",
                "гость", "телефон гостя"]


def phone_key(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:]


def _rub(v) -> str:
    return f"{Decimal(v):,.0f}".replace(",", " ") + " ₽"


def _short(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def render_message(body: str, b: dict, prop: dict, room_name: str, extra: dict | None = None) -> str:
    nights = (b["check_out"] - b["check_in"]).days
    n_word = "ночь" if nights % 10 == 1 and nights % 100 != 11 else ("ночи" if 2 <= nights % 10 <= 4 and not 12 <= nights % 100 <= 14 else "ночей")
    values = {
        "имя": (b["guest_name"] or "гость").split()[0] if b["guest_name"] else "гость",
        "даты": f"{b['check_in'].strftime('%d.%m')}–{_short(b['check_out'])}",
        "заезд": _short(b["check_in"]), "выезд": _short(b["check_out"]), "ночей": str(nights), "срок": f"{nights} {n_word}",
        "номер": room_name, "объект": prop["name"], "адрес": prop["address"] or "—", "телефон объекта": prop["phone"] or "—",
        "время заезда": prop["check_in_time"].strftime("%H:%M"), "время выезда": prop["check_out_time"].strftime("%H:%M"),
        "гость": (b["guest_name"] or "гость без имени").strip(), "телефон гостя": b["guest_phone"] or "—",
        "сумма": _rub(b["total_price"]), "сумма к оплате": _rub(max(Decimal(b["total_price"]) - Decimal(b["paid_amount"]), 0)),
    }
    values.update(extra or {})
    return re.sub(r"\{([^{}]+)\}", lambda m: values.get(m.group(1).strip().lower(), m.group(0)), body)


def message_extras(conn, body: str, b: dict) -> dict:
    """Значения «дорогих» подстановок — только тех, что есть в тексте (ссылки создают секретные токены в базе)."""
    from .. import guestlinks
    low = body.lower()
    extra: dict = {}
    if "{код двери" in low:
        code = (b.get("door_code") or "").strip()
        if not code:
            r = one(conn, "SELECT door_code FROM rooms WHERE id = %s", (b["room_id"],))
            code = (r["door_code"] if r else "").strip()
        extra["код двери"] = code or "уточните у администратора"
    if "{ссылка на анкету" in low:
        extra["ссылка на анкету"] = guestlinks.form_url(guestlinks.ensure_form(conn, b["account_id"], b["id"]))
    if "{ссылка на отзыв" in low:
        extra["ссылка на отзыв"] = guestlinks.review_url(guestlinks.ensure_review(conn, b))
    return extra


def _ensure_templates(conn, account_id) -> None:
    if not one(conn, "SELECT 1 FROM message_templates WHERE account_id = %s LIMIT 1", (account_id,)):
        for i, (name, body) in enumerate(DEFAULT_TEMPLATES):
            run(conn, "INSERT INTO message_templates (account_id, name, body, sort_order) VALUES (%s, %s, %s, %s)",
                (account_id, name, body, i))


def flags_for(conn, account_id, bookings: list[dict]) -> dict:
    """Пометки для шахматки: чёрный список и день рождения гостя во время проживания."""
    keys = {phone_key(b["guest_phone"]) for b in bookings if b.get("guest_phone")}
    keys.discard("")
    if not keys:
        return {}
    profiles = {p["phone_key"]: p for p in all_(
        conn, "SELECT phone_key, birthday, blacklisted FROM guest_profiles WHERE account_id = %s AND phone_key = ANY(%s)"
              " AND (blacklisted OR birthday IS NOT NULL)", (account_id, list(keys)))}
    out = {}
    for b in bookings:
        p = profiles.get(phone_key(b.get("guest_phone") or ""))
        if not p:
            continue
        flag = {}
        if p["blacklisted"]:
            flag["blacklisted"] = True
        if p["birthday"]:
            d = b["check_in"]
            while d < b["check_out"]:
                if (d.month, d.day) == (p["birthday"].month, p["birthday"].day):
                    flag["birthday"] = d.isoformat()
                    break
                d = date.fromordinal(d.toordinal() + 1)
        if flag:
            out[str(b["id"])] = flag
    return out


def _stays(conn, account_id, key: str) -> list[dict]:
    return all_(conn, "SELECT b.id, b.check_in, b.check_out, b.status, b.source, b.total_price, b.paid_amount, b.guest_name,"
                      " b.guest_phone, r.name AS room_name, p.name AS property_name FROM bookings b"
                      " JOIN rooms r ON r.id = b.room_id JOIN properties p ON p.id = b.property_id"
                      f" WHERE b.account_id = %s AND {BK_KEY} = %s AND b.guest_phone <> '' AND b.status <> 'blocked'"
                      " ORDER BY b.check_in DESC LIMIT 200", (account_id, key))


def _profile(conn, account_id, key: str) -> dict:
    p = one(conn, "SELECT name, tags, notes, birthday, blacklisted, blacklist_reason FROM guest_profiles"
                  " WHERE account_id = %s AND phone_key = %s", (account_id, key))
    return p or {"name": "", "tags": [], "notes": "", "birthday": None, "blacklisted": False, "blacklist_reason": ""}


@api("manager")
def guest_card(c: Ctx):
    """Карточка гостя: профиль, итоги и история проживаний (по телефону, любой формат записи)."""
    phone = (c.q.get("phone") or "").strip()
    key = phone_key(phone)
    if len(key) < 5:
        raise ApiError(422, "Укажите телефон гостя")
    with tx() as conn:
        stays = _stays(conn, c.account_id, key)
        profile = _profile(conn, c.account_id, key)
    real = [s for s in stays if s["status"] != "cancelled"]
    return {"phone": phone, "key": key, "profile": profile, "visits": len(real), "returning": len(real) >= 2,
            "nights": sum((s["check_out"] - s["check_in"]).days for s in real),
            "total_spent": sum((s["total_price"] for s in real), Decimal("0")),
            "total_paid": sum((s["paid_amount"] for s in real), Decimal("0")),
            "cancelled": len(stays) - len(real), "stays": stays}


@api("manager")
def guest_check(c: Ctx):
    """Быстрая проверка по телефону при создании брони: чёрный список, постоянный гость, день рождения."""
    key = phone_key(c.q.get("phone") or "")
    if len(key) < 10:
        return {"known": False}
    with tx() as conn:
        profile = _profile(conn, c.account_id, key)
        row = one(conn, "SELECT count(*) AS n, max(b.guest_name) AS name FROM bookings b WHERE b.account_id = %s"
                        f" AND {BK_KEY} = %s AND b.guest_phone <> '' AND b.status IN ('confirmed', 'pending')",
                  (c.account_id, key))
    return {"known": bool(row["n"] or profile["blacklisted"] or profile["tags"] or profile["notes"]),
            "visits": row["n"], "returning": row["n"] >= 2, "name": row["name"] or profile["name"],
            "blacklisted": profile["blacklisted"], "blacklist_reason": profile["blacklist_reason"],
            "tags": profile["tags"], "notes": profile["notes"], "birthday": profile["birthday"]}


@api("manager")
def list_guests(c: Ctx):
    q = (c.q.get("q") or "").strip()
    sort = c.q.get("sort") or "last"
    order = {"last": "last_stay DESC", "visits": "visits DESC, last_stay DESC", "spent": "spent DESC, last_stay DESC",
             "name": "name"}.get(sort)
    if not order:
        raise ApiError(422, "Неверная сортировка")
    page = parse_int(c.q.get("page"), "Страница", 1, default=1)
    like = f"%{q.replace('%', '').replace('_', '')}%"
    with tx() as conn:
        rows = all_(conn, f"""
            WITH g AS (
              SELECT {BK_KEY} AS key,
                     (array_agg(b.guest_name ORDER BY b.check_in DESC))[1] AS name,
                     (array_agg(b.guest_phone ORDER BY b.check_in DESC))[1] AS phone,
                     count(*) FILTER (WHERE b.status IN ('confirmed', 'pending')) AS visits,
                     coalesce(sum(b.check_out - b.check_in) FILTER (WHERE b.status IN ('confirmed', 'pending')), 0) AS nights,
                     coalesce(sum(b.total_price) FILTER (WHERE b.status IN ('confirmed', 'pending')), 0) AS spent,
                     max(b.check_in) AS last_stay,
                     min(b.check_in) FILTER (WHERE b.check_in >= current_date AND b.status IN ('confirmed', 'pending')) AS next_stay
              FROM bookings b WHERE b.account_id = %s AND b.guest_phone <> '' AND b.status <> 'blocked'
              GROUP BY 1 HAVING length({BK_KEY}) >= 5)
            SELECT g.*, coalesce(p.tags, '{{}}') AS tags, coalesce(p.blacklisted, false) AS blacklisted, p.notes, p.birthday
            FROM g LEFT JOIN guest_profiles p ON p.account_id = %s AND p.phone_key = g.key
            WHERE (%s = '' OR g.name ILIKE %s OR g.phone ILIKE %s OR g.key LIKE %s OR %s = ANY(coalesce(p.tags, '{{}}')))
            ORDER BY {order}, g.key LIMIT 51 OFFSET %s""",
                    (c.account_id, c.account_id, q, like, like, "%" + re.sub(r"\D", "", q) + "%" if re.sub(r"\D", "", q) else "~~", q.lower(), (page - 1) * 50))
    return {"items": rows[:50], "more": len(rows) > 50, "page": page}


@api("manager")
def save_profile(c: Ctx):
    d = c.data
    key = phone_key(d.get("phone") or "")
    if len(key) < 5:
        raise ApiError(422, "Укажите телефон гостя", {"field": "phone"})
    tags = d.get("tags") or []
    if not isinstance(tags, list) or len(tags) > 12:
        raise ApiError(422, "Тегов может быть не больше 12")
    tags = list(dict.fromkeys(str(t).strip().lower()[:30] for t in tags if str(t).strip()))
    birthday = parse_date(d["birthday"], "День рождения", "birthday") if d.get("birthday") else None
    black = bool(d.get("blacklisted"))
    reason = opt_str(d, "blacklist_reason", max_len=300)
    if black and not reason:
        raise ApiError(422, "Укажите причину, чтобы не забыть, почему гость в чёрном списке", {"field": "blacklist_reason"})
    with tx() as conn:
        old = _profile(conn, c.account_id, key)
        row = one(conn, "INSERT INTO guest_profiles (account_id, phone_key, name, tags, notes, birthday, blacklisted, blacklist_reason)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (account_id, phone_key) DO UPDATE SET"
                        " name = EXCLUDED.name, tags = EXCLUDED.tags, notes = EXCLUDED.notes, birthday = EXCLUDED.birthday,"
                        " blacklisted = EXCLUDED.blacklisted, blacklist_reason = EXCLUDED.blacklist_reason, updated_at = now()"
                        " RETURNING name, tags, notes, birthday, blacklisted, blacklist_reason",
                  (c.account_id, key, opt_str(d, "name", max_len=200), tags, opt_str(d, "notes", max_len=2000), birthday, black, reason))
        if black != old["blacklisted"]:
            from .. import audit
            audit.record(conn, c.account_id, c.p.user_id, "guest_blacklist", f"{'Добавлен в чёрный список' if black else 'Убран из чёрного списка'}: {d.get('name') or d.get('phone')}"
                         + (f" ({reason})" if black else ""))
    return row


# ---------- шаблоны сообщений ----------
@api("manager")
def list_templates(c: Ctx):
    with tx() as conn:
        _ensure_templates(conn, c.account_id)
        rows = all_(conn, "SELECT id, name, body FROM message_templates WHERE account_id = %s ORDER BY sort_order, created_at", (c.account_id,))
    return {"items": rows, "placeholders": PLACEHOLDERS}


@api("manager")
def create_template(c: Ctx):
    name, body = req_str(c.data, "name", "Название", 100), req_str(c.data, "body", "Текст", 2000)
    with tx() as conn:
        if one(conn, "SELECT count(*) AS n FROM message_templates WHERE account_id = %s", (c.account_id,))["n"] >= 30:
            raise ApiError(422, "Слишком много шаблонов")
        return one(conn, "INSERT INTO message_templates (account_id, name, body, sort_order) VALUES (%s, %s, %s,"
                         " (SELECT coalesce(max(sort_order), 0) + 1 FROM message_templates WHERE account_id = %s)) RETURNING id, name, body",
                   (c.account_id, name, body, c.account_id))


@api("manager")
def update_template(c: Ctx):
    tid = parse_uuid(c.path["id"], "Шаблон")
    name, body = req_str(c.data, "name", "Название", 100), req_str(c.data, "body", "Текст", 2000)
    with tx() as conn:
        row = one(conn, "UPDATE message_templates SET name = %s, body = %s WHERE id = %s AND account_id = %s RETURNING id, name, body",
                  (name, body, tid, c.account_id))
    if not row:
        raise ApiError(404, "Шаблон не найден")
    return row


@api("manager")
def delete_template(c: Ctx):
    with tx() as conn:
        if not run(conn, "DELETE FROM message_templates WHERE id = %s AND account_id = %s", (parse_uuid(c.path["id"], "Шаблон"), c.account_id)):
            raise ApiError(404, "Шаблон не найден")
    return {"ok": True}


def _booking_ctx(conn, account_id, booking_id):
    b = one(conn, "SELECT * FROM bookings WHERE id = %s AND account_id = %s", (parse_uuid(booking_id, "Бронь"), account_id))
    if not b or b["status"] == "blocked":
        raise ApiError(404, "Бронь не найдена")
    prop = one(conn, "SELECT * FROM properties WHERE id = %s", (b["property_id"],))
    room = one(conn, "SELECT name FROM rooms WHERE id = %s", (b["room_id"],))
    return b, prop, room["name"]


@api("manager")
def render_for_booking(c: Ctx):
    """Текст сообщения гостю из шаблона (или своего текста) с подстановкой данных брони."""
    with tx() as conn:
        b, prop, room = _booking_ctx(conn, c.account_id, c.path["id"])
        body = c.data.get("body")
        if not body and c.data.get("template_id"):
            t = one(conn, "SELECT body FROM message_templates WHERE id = %s AND account_id = %s",
                    (parse_uuid(c.data["template_id"], "Шаблон"), c.account_id))
            if not t:
                raise ApiError(404, "Шаблон не найден")
            body = t["body"]
        if not body:
            raise ApiError(422, "Выберите шаблон или введите текст")
        share = f"{config.PUBLIC_BASE_URL}/book/{prop['public_slug']}" if prop["booking_enabled"] else config.PUBLIC_BASE_URL
        extra = message_extras(conn, str(body)[:3000], b)
    text = render_message(str(body)[:3000], b, prop, room, extra)
    return {"text": text, "email": b["guest_email"], "phone": b["guest_phone"],
            "subject": f"{prop['name']}: бронирование {b['check_in'].strftime('%d.%m')}–{b['check_out'].strftime('%d.%m')}",
            "share_url": share}


@api("manager")
def send_email_to_guest(c: Ctx):
    text = req_str(c.data, "text", "Текст письма", 5000)
    subject = req_str(c.data, "subject", "Тема", 200)
    with tx() as conn:
        b, prop, room = _booking_ctx(conn, c.account_id, c.path["id"])
        if not b["guest_email"] or "@" not in b["guest_email"]:
            raise ApiError(422, "У гостя не указан email — добавьте его в карточке брони")
        booklog.log(conn, c.account_id, b["id"], c.p.user_id, "message", {"summary": f"Письмо гостю: «{subject}»"})
    try:
        mail.send_or_log(b["guest_email"], subject, text)
    except Exception:
        raise ApiError(502, "Не удалось отправить письмо. Скопируйте текст и отправьте сами — или проверьте настройки почты")
    return {"ok": True, "to": b["guest_email"], "configured": mail.configured()}


routes = [
    Route("/api/guests/card", guest_card),
    Route("/api/guests/check", guest_check),
    Route("/api/guests/list", list_guests),
    Route("/api/guests/profile", save_profile, methods=["PUT"]),
    Route("/api/message-templates", list_templates),
    Route("/api/message-templates", create_template, methods=["POST"]),
    Route("/api/message-templates/{id}", update_template, methods=["PATCH"]),
    Route("/api/message-templates/{id}", delete_template, methods=["DELETE"]),
    Route("/api/bookings/{id}/message", render_for_booking, methods=["POST"]),
    Route("/api/bookings/{id}/message/email", send_email_to_guest, methods=["POST"]),
]
