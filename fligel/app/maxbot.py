"""Уведомления в мессенджер MAX — второй канал рядом с Telegram (app/telegram.py).

Полностью выключено, пока не задан MAX_BOT_TOKEN: enabled() вернёт False, а notify()/process_outbox()/
maybe_send_digests() ничего не делают — ни одного запроса к MAX не будет, пока владелец сам не создаст
бота и не впишет токен. Привязка — по коду: сотрудник открывает ссылку https://max.ru/<бот>?start=<код>
(или пишет боту «/start <код>»), бот присылает событие, мы связываем чат с сотрудником.

ВАЖНО: адаптер написан по описанию Bot API платформы MAX (https://dev.max.ru/docs-api) без проверки
на живом токене. Что проверить при подключении, перечислено в PROGRESS.md («Что проверить на живом токене»).
"""
import logging
import secrets
from datetime import datetime

import httpx

from . import config, outbox
from .db import all_, one, run, tx
from .telegram import EVENTS, EVENT_LABELS, LINK_CODE_TTL_MINUTES, MAX_ATTEMPTS, _digest_text  # те же события и тексты

log = logging.getLogger("fligel.max")

__all__ = ["EVENTS", "EVENT_LABELS"]


def enabled() -> bool:
    return bool(config.MAX_BOT_TOKEN)


def deep_link(code: str) -> str | None:
    """Ссылка, по которой сотрудник открывает бота и привязывает чат одним нажатием."""
    return f"https://max.ru/{config.MAX_BOT_USERNAME}?start={code}" if config.MAX_BOT_USERNAME else None


# ---------- привязка ----------

def start_link(conn, account_id: str, user_id: str) -> dict:
    code = secrets.token_hex(4).upper()
    return one(
        conn,
        "INSERT INTO max_links (account_id, user_id, link_code, link_code_expires_at)"
        " VALUES (%s, %s, %s, now() + make_interval(mins => %s))"
        " ON CONFLICT (user_id) DO UPDATE SET link_code = EXCLUDED.link_code,"
        " link_code_expires_at = EXCLUDED.link_code_expires_at RETURNING link_code, link_code_expires_at",
        (account_id, user_id, code, LINK_CODE_TTL_MINUTES),
    )


def get_link(conn, user_id: str) -> dict | None:
    return one(conn, "SELECT chat_id, linked_at, link_code, link_code_expires_at, events, enabled"
                     " FROM max_links WHERE user_id = %s", (user_id,))


def unlink(conn, user_id: str) -> None:
    run(conn, "UPDATE max_links SET chat_id = NULL, linked_at = NULL, link_code = NULL, link_code_expires_at = NULL"
              " WHERE user_id = %s", (user_id,))


def set_events(conn, account_id: str, user_id: str, events: list, enabled_flag: bool | None = None) -> list:
    chosen = [e for e in EVENTS if e in (events or [])]
    run(conn, "INSERT INTO max_links (account_id, user_id, events, enabled) VALUES (%s, %s, %s, coalesce(%s, true))"
              " ON CONFLICT (user_id) DO UPDATE SET events = EXCLUDED.events,"
              " enabled = coalesce(%s, max_links.enabled)", (account_id, user_id, chosen, enabled_flag, enabled_flag))
    return chosen


def handle_start(conn, code: str, chat_id: int) -> bool:
    row = one(conn, "SELECT id, account_id FROM max_links WHERE link_code = %s AND link_code_expires_at > now()",
              (str(code).strip().upper(),))
    if not row:
        return False
    run(conn, "UPDATE max_links SET chat_id = %s, linked_at = now(), link_code = NULL, link_code_expires_at = NULL"
              " WHERE id = %s", (chat_id, row["id"]))
    enqueue(conn, row["account_id"], chat_id, "Готово! Уведомления «Флигель» подключены к этому чату.")
    return True


def parse_update(update: dict) -> tuple[int | None, str]:
    """Достаёт (chat_id, код привязки) из события вебхука MAX. Понимаем оба варианта: «bot_started»
    (человек нажал «Начать» по ссылке с ?start=<код>) и обычное сообщение «/start <код>» / просто код."""
    kind = update.get("update_type")
    if kind == "bot_started":
        return update.get("chat_id"), str(update.get("payload") or "").strip()
    if kind == "message_created":
        msg = update.get("message") or {}
        chat_id = (msg.get("recipient") or {}).get("chat_id") or update.get("chat_id")
        text = str((msg.get("body") or {}).get("text") or "").strip()
        if text.lower().startswith("/start"):
            text = text[6:].strip()
        return chat_id, text if len(text) <= 16 else ""
    return None, ""


# ---------- очередь отправки ----------

def enqueue(conn, account_id: str, chat_id: int, text: str) -> None:
    run(conn, "INSERT INTO max_outbox (account_id, chat_id, text) VALUES (%s, %s, %s)", (account_id, chat_id, text))


def notify(conn, account_id: str, event: str, text: str) -> int:
    if not enabled():
        return 0
    rows = all_(conn, "SELECT chat_id FROM max_links WHERE account_id = %s AND chat_id IS NOT NULL AND enabled"
                      " AND %s = ANY(events)", (account_id, event))
    for r in rows:
        enqueue(conn, account_id, r["chat_id"], text)
    return len(rows)


def _default_send(chat_id: int, text: str) -> None:
    """Настоящая отправка через Bot API MAX (только при заданном MAX_BOT_TOKEN). В тестах подменяется моком."""
    resp = httpx.post(f"{config.MAX_API_BASE}/messages", params={"chat_id": chat_id},
                      headers={"Authorization": config.MAX_BOT_TOKEN}, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"MAX ответил кодом {resp.status_code}: {resp.text[:300]}")


send_message = _default_send


def process_outbox(limit: int = 20) -> dict:
    """Отправка с повторами (2, 4, 8… минут, не дольше часа); после MAX_ATTEMPTS попыток — status='failed'. Без транзакции на время запроса."""
    if not enabled():
        return {"sent": 0, "failed": 0}
    outbox.recover("max_outbox")
    rows = outbox.claim("max_outbox", "SELECT id, chat_id, text, attempts FROM max_outbox WHERE status = 'pending'"
                                      " AND next_attempt_at <= now() ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED", (limit,))
    sent = failed = 0
    for row in rows:
        try:
            send_message(row["chat_id"], row["text"])
        except Exception as e:  # noqa: BLE001
            try:
                if outbox.mark_retry("max_outbox", row, str(e), MAX_ATTEMPTS):
                    failed += 1
                    log.warning("Сообщение в MAX не отправлено после %s попыток: %s", row["attempts"] + 1, e)
            except Exception:  # noqa: BLE001
                log.exception("Не удалось записать ошибку отправки %s", row["id"])
            continue
        try:
            outbox.mark_sent("max_outbox", row["id"])
        except Exception:  # noqa: BLE001 — сообщение уже ушло; остальные захваченные не бросаем в 'sending'
            log.exception("Не удалось отметить отправленным сообщение %s", row["id"])
        sent += 1
    return {"sent": sent, "failed": failed}


def maybe_send_digests(now: datetime | None = None) -> int:
    if not enabled():
        return 0
    now = now or datetime.now()
    if now.hour < config.TELEGRAM_DIGEST_HOUR:
        return 0
    today = now.date()
    sent = 0
    with tx() as conn:
        for a in all_(conn, "SELECT DISTINCT account_id FROM max_links WHERE chat_id IS NOT NULL AND enabled AND 'digest' = ANY(events)"):
            account_id = a["account_id"]
            if one(conn, "SELECT 1 FROM max_digest_log WHERE account_id = %s AND last_sent_date = %s", (account_id, today)):
                continue
            notify(conn, account_id, "digest", _digest_text(conn, account_id, today))
            run(conn, "INSERT INTO max_digest_log (account_id, last_sent_date) VALUES (%s, %s)"
                      " ON CONFLICT (account_id) DO UPDATE SET last_sent_date = EXCLUDED.last_sent_date", (account_id, today))
            sent += 1
    return sent
