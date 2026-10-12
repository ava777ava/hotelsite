"""Автопилот: правила «событие → условие → действие», которые выполняются сами.

Раз в проход планировщика (sync.run_once) для каждого включённого правила находятся брони, подходящие по событию и
условиям, и над каждой бронью правило срабатывает ровно один раз (уникальность в automation_runs). Если сервис
простоял день, правило «догоняет» пропущенное окно (см. _CANDIDATES), поэтому сообщение не теряется.

Действия: сообщение сотрудникам (колокольчик + Telegram/MAX), письмо гостю по шаблону, задача сотруднику,
статус уборки номера. Письма отправляются уже после коммита записи о срабатывании, чтобы медленная почта не держала транзакцию."""
import json
import logging

from . import mail, notify
from .api import guests as guestapi
from .api import tasks as taskapi
from .db import all_, one, run, tx

log = logging.getLogger("fligel.automation")

EVENTS = {
    "before_checkin": "За N дней до заезда",
    "checkin_day": "В день заезда",
    "checkout_day": "В день выезда",
    "after_checkout": "Через N дней после выезда",
    "new_booking": "Появилась новая бронь",
    "debt": "Остался долг после выезда (через N дней, 0 — в день выезда)",
}
ACTIONS = {
    "notify_staff": "Сообщение сотрудникам (колокольчик, Telegram, MAX)",
    "email_guest": "Письмо гостю",
    "create_task": "Задача сотруднику",
    "set_cleaning": "Номер — «нужна уборка»",
}
OVERDUE_HOUR = 9  # с какого часа раз в день напоминаем о просроченных задачах

# Условие отбора броней для каждого события: SQL про b (бронь) и r (правило). Окно «догоняет» пропущенные дни.
_CANDIDATES = {
    "before_checkin": "b.check_in - r.offset_days <= current_date AND current_date < b.check_in",
    "checkin_day": "b.check_in = current_date",
    "checkout_day": "b.check_out = current_date",
    "after_checkout": "b.check_out + r.offset_days <= current_date AND current_date <= b.check_out + r.offset_days + 2",
    "new_booking": "b.created_at > r.created_at AND b.created_at > now() - interval '3 days'",
    "debt": "b.check_out + r.offset_days <= current_date AND current_date <= b.check_out + r.offset_days + 2"
            " AND b.total_price - b.paid_amount > 0",
}

_INSTRUCTIONS = ("Здравствуйте, {имя}! Завтра ждём вас: {объект}, номер {номер}, заезд с {время заезда}.\nАдрес: {адрес}.\n"
                 "Код двери: {код двери}.\nЕсли поменялись планы или нужна помощь — звоните: {телефон объекта}.")
_PAYMENT = ("Здравствуйте, {имя}! Напоминаем про оплату бронирования {даты} ({объект}): осталось внести {сумма к оплате}. "
            "Если уже оплатили — не обращайте внимания на это письмо. Вопросы: {телефон объекта}.")
_FORM = ("Здравствуйте, {имя}! До заезда ({объект}, {заезд}) осталось немного. Расскажите, пожалуйста, когда вы приедете и что "
         "нам подготовить — это займёт минуту: {ссылка на анкету}\nПаспортные данные не нужны.")
_REVIEW = ("{имя}, спасибо, что остановились у нас ({объект})! Нам важно ваше мнение — поставьте оценку и напишите пару слов: "
           "{ссылка на отзыв}\nЭто займёт минуту и поможет нам стать лучше.")

# Готовые сценарии. Создаются каждому аккаунту; каждый можно выключить. enabled — значение по умолчанию для НОВОГО аккаунта.
PRESETS = [
    {"key": "checkin_instructions", "name": "Инструкция по заселению за день до приезда", "event": "before_checkin", "offset_days": 1, "at_hour": 12,
     "action": "email_guest", "enabled": True, "params": {"subject": "{объект}: как заселиться {заезд}", "body": _INSTRUCTIONS},
     "hint": "Гостю с email уходит письмо с адресом и кодом двери."},
    {"key": "payment_reminder", "name": "Напоминание об оплате за 3 дня до заезда", "event": "before_checkin", "offset_days": 3, "at_hour": 10,
     "only_unpaid": True, "action": "email_guest", "enabled": True,
     "params": {"subject": "{объект}: напоминание об оплате брони {даты}", "body": _PAYMENT}, "hint": "Только если по брони остался долг."},
    {"key": "cleaning_after_checkout", "name": "Уборка после выезда", "event": "checkout_day", "offset_days": 0, "at_hour": 12,
     "action": "set_cleaning", "enabled": True, "params": {"status": "dirty", "notify": True},
     "hint": "В день выезда номер получает статус «нужна уборка», сотрудники видят сообщение."},
    {"key": "questionnaire", "name": "Анкета гостя за 3 дня до приезда", "event": "before_checkin", "offset_days": 3, "at_hour": 11,
     "action": "email_guest", "enabled": False, "params": {"subject": "{объект}: расскажите, когда приедете", "body": _FORM},
     "hint": "Письмо со ссылкой на анкету: время приезда, число гостей, машина, пожелания. Паспорт не запрашивается."},
    {"key": "review_request", "name": "Просьба об отзыве на следующий день после выезда", "event": "after_checkout", "offset_days": 1, "at_hour": 11,
     "action": "email_guest", "enabled": False, "params": {"subject": "{объект}: как вам проживание?", "body": _REVIEW},
     "hint": "Ссылка на оценку 1–5. Отзывы видны только вам; низкая оценка сразу приходит уведомлением."},
    {"key": "debt_alert", "name": "Долг по брони в день выезда", "event": "debt", "offset_days": 0, "at_hour": 12,
     "action": "notify_staff", "enabled": True, "params": {"text": "Гость {гость} выезжает, а не оплачено {сумма к оплате} (номер {номер}). Телефон: {телефон гостя}."},
     "hint": "Сообщение сотрудникам, чтобы не отпустить гостя без расчёта."},
]
PRESET_KEYS = {p["key"] for p in PRESETS}


def ensure_presets(conn, account_id, use_defaults: bool) -> None:
    """Создаёт недостающие готовые сценарии. use_defaults=False — все выключены (старые аккаунты ничего не получают без их ведома)."""
    for p in PRESETS:
        run(conn, "INSERT INTO automation_rules (account_id, preset, name, event, offset_days, at_hour, only_unpaid, action, params, enabled)"
                  " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (account_id, preset) WHERE preset IS NOT NULL DO NOTHING",
            (account_id, p["key"], p["name"], p["event"], p["offset_days"], p["at_hour"], p.get("only_unpaid", False),
             p["action"], json.dumps(p["params"], ensure_ascii=False), bool(p["enabled"] and use_defaults)))


# ---------- выполнение ----------

def _render(conn, text: str, b: dict) -> str:
    prop = one(conn, "SELECT * FROM properties WHERE id = %s", (b["property_id"],))
    room = one(conn, "SELECT name FROM rooms WHERE id = %s", (b["room_id"],))
    return guestapi.render_message(text, b, prop, room["name"], guestapi.message_extras(conn, text, b))


def _act_notify_staff(conn, rule: dict, b: dict) -> tuple[str, str, None]:
    text = _render(conn, str(rule["params"].get("text") or "Сработал сценарий «{}»").replace("{}", rule["name"]), b)
    notify.send(conn, b["account_id"], "automation", text, link="#/bookings", bell=True)
    return "done", "Сообщение сотрудникам отправлено", None


def _act_create_task(conn, rule: dict, b: dict) -> tuple[str, str, None]:
    p = rule["params"]
    title = _render(conn, str(p.get("title") or "Задача по брони {гость}"), b)
    due = one(conn, "SELECT (current_date + %s::int) AS d", (int(p.get("due_in_days") or 0),))["d"]
    assignee = p.get("assignee_id") or None
    if assignee and not one(conn, "SELECT 1 FROM users WHERE id = %s AND account_id = %s", (assignee, b["account_id"])):
        assignee = None
    taskapi.create_task(conn, b["account_id"], title, description=_render(conn, str(p.get("description") or ""), b),
                        assignee_id=assignee, due_date=due, room_id=b["room_id"], booking_id=b["id"], source="automation")
    if p.get("notify", True):
        notify.send(conn, b["account_id"], "task", f"Новая задача (автопилот): {title}", link="#/tasks", bell=True)
    return "done", f"Создана задача «{title}»", None


def _act_set_cleaning(conn, rule: dict, b: dict) -> tuple[str, str, None]:
    status = rule["params"].get("status") if rule["params"].get("status") in ("dirty", "inspect") else "dirty"
    room = one(conn, "SELECT id, name, hk_status, cleaned_on FROM rooms WHERE id = %s FOR UPDATE", (b["room_id"],))
    if room["hk_status"] != "clean":
        return "skipped", f"Номер {room['name']} уже имеет статус уборки — не меняли", None
    if room["cleaned_on"] and room["cleaned_on"] >= b["check_out"]:
        return "skipped", f"Номер {room['name']} уже убран после выезда", None
    run(conn, "UPDATE rooms SET hk_status = %s, hk_note = '', hk_updated_at = now() WHERE id = %s", (status, room["id"]))
    run(conn, "INSERT INTO room_status_log (account_id, room_id, user_id, status, note) VALUES (%s, %s, NULL, %s, %s)",
        (b["account_id"], room["id"], status, f"Автопилот: {rule['name']}"))
    if rule["params"].get("notify", True):
        notify.send(conn, b["account_id"], "automation", f"Номер {room['name']}: нужна уборка после выезда гостя {b['guest_name'] or 'без имени'}.",
                    link="#/cleaning", bell=True)
    return "done", f"Номер {room['name']}: нужна уборка", None


def _prepare_email(conn, rule: dict, b: dict) -> tuple[str, str, tuple | None]:
    """Готовит письмо внутри транзакции; отправка — после неё. Третий элемент: (кому, тема, текст) или None."""
    to = (b["guest_email"] or "").strip()
    subject = _render(conn, str(rule["params"].get("subject") or "{объект}: сообщение для вас"), b)[:200]
    if "@" not in to:
        if rule["params"].get("notify_if_missing", True):
            notify.send(conn, b["account_id"], "automation",
                        f"Не отправлено письмо «{subject}» гостю {b['guest_name'] or 'без имени'}: не указан email. Отправьте сообщение вручную "
                        "(в карточке брони — «Написать гостю»).", link="#/bookings", bell=True)
        return "skipped", "У гостя нет email — письмо не отправлено, сотрудникам отправлено напоминание", None
    if not mail.configured():
        return "skipped", "Почта (SMTP) на сервере не настроена — письмо не отправлено", None
    return "done", f"Письмо отправлено на {to}", (to, subject, _render(conn, str(rule["params"].get("body") or ""), b))


_DB_ACTIONS = {"notify_staff": _act_notify_staff, "create_task": _act_create_task, "set_cleaning": _act_set_cleaning}


def _fire(rule: dict, bid) -> str | None:
    """Выполняет правило по одной брони. Возвращает итоговый статус или None, если по этой брони правило уже срабатывало."""
    outbox = None
    with tx() as conn:
        claimed = one(conn, "INSERT INTO automation_runs (account_id, rule_id, booking_id) VALUES (%s, %s, %s)"
                            " ON CONFLICT (rule_id, booking_id) DO NOTHING RETURNING id", (rule["account_id"], rule["id"], bid))
        if not claimed:
            return None
        b = one(conn, "SELECT * FROM bookings WHERE id = %s", (bid,))
        try:
            with conn.transaction():  # сбой действия не должен отменять запись о срабатывании
                if rule["action"] == "email_guest":
                    status, detail, outbox = _prepare_email(conn, rule, b)
                else:
                    status, detail, _ = _DB_ACTIONS[rule["action"]](conn, rule, b)
        except Exception as e:  # noqa: BLE001
            log.exception("Сбой действия автопилота %s", rule["id"])
            status, detail, outbox = "error", f"Ошибка: {str(e)[:200]}", None
        run(conn, "UPDATE automation_runs SET status = %s, detail = %s WHERE id = %s", (status, detail[:500], claimed["id"]))
    if outbox:
        try:
            mail.send_or_log(*outbox)
        except Exception as e:  # noqa: BLE001
            log.warning("Письмо автопилота не отправлено: %s", e)
            status = "error"
            with tx() as conn:
                run(conn, "UPDATE automation_runs SET status = 'error', detail = %s WHERE rule_id = %s AND booking_id = %s",
                    (f"Не удалось отправить письмо: {str(e)[:200]}", rule["id"], bid))
    return status


def run_rule(rule: dict, limit: int = 200) -> int:
    where = _CANDIDATES[rule["event"]]
    cond = ["b.account_id = r.account_id", "b.status = 'confirmed'", where,
            "NOT EXISTS (SELECT 1 FROM automation_runs ar WHERE ar.rule_id = r.id AND ar.booking_id = b.id)"]
    if rule["event"] != "new_booking":
        cond.append("extract(hour from now()) >= r.at_hour")
    if rule["only_unpaid"]:
        cond.append("b.total_price - b.paid_amount > 0")
    if rule["sources"]:
        cond.append("b.source = ANY(r.sources)")
    if rule["property_id"]:
        cond.append("b.property_id = r.property_id")
    with tx() as conn:
        ids = [x["id"] for x in all_(conn, f"SELECT b.id FROM bookings b JOIN automation_rules r ON r.id = %s WHERE {' AND '.join(cond)}"
                                           " ORDER BY b.check_in LIMIT %s", (rule["id"], limit))]
    fired = 0
    for bid in ids:
        try:
            if _fire(rule, bid) is not None:
                fired += 1
        except Exception:  # noqa: BLE001
            log.exception("Автопилот: правило %s, бронь %s", rule["id"], bid)
    return fired


def notify_overdue_tasks() -> int:
    """Раз в день напоминает владельцу и администраторам о просроченных задачах (одно сообщение на аккаунт)."""
    sent = 0
    with tx() as conn:
        accounts = all_(conn, "SELECT t.account_id, count(*) AS n, min(t.title) AS first_title FROM tasks t JOIN accounts a ON a.id = t.account_id"
                              " WHERE a.status = 'active' AND 'tasks' = ANY(a.modules) AND t.done_at IS NULL AND t.due_date < current_date"
                              " AND (t.overdue_notified_on IS NULL OR t.overdue_notified_on < current_date)"
                              " AND extract(hour from now()) >= %s GROUP BY t.account_id", (OVERDUE_HOUR,))
        for a in accounts:
            run(conn, "UPDATE tasks SET overdue_notified_on = current_date WHERE account_id = %s AND done_at IS NULL AND due_date < current_date",
                (a["account_id"],))
            word = "задача" if a["n"] % 10 == 1 and a["n"] % 100 != 11 else ("задачи" if 2 <= a["n"] % 10 <= 4 and not 12 <= a["n"] % 100 <= 14 else "задач")
            notify.send(conn, a["account_id"], "task", f"Просрочено: {a['n']} {word} — например, «{a['first_title']}». Откройте раздел «Задачи».",
                        link="#/tasks", bell=True)
            sent += 1
    return sent


def run_due() -> int:
    """Один проход автопилота по всем включённым правилам (вызывается планировщиком)."""
    with tx() as conn:
        rules = all_(conn, "SELECT r.* FROM automation_rules r JOIN accounts a ON a.id = r.account_id WHERE r.enabled AND a.status = 'active' AND 'autopilot' = ANY(a.modules)")
    fired = 0
    for rule in rules:
        try:
            fired += run_rule(rule)
        except Exception:  # noqa: BLE001
            log.exception("Автопилот: сбой правила %s", rule["id"])
    try:
        notify_overdue_tasks()
    except Exception:  # noqa: BLE001
        log.exception("Автопилот: напоминание о просроченных задачах")
    return fired
