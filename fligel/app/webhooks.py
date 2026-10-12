"""Вебхуки: события броней уходят на адрес клиента (подпись HMAC-SHA256, повторы с растущей паузой).

События ставятся в очередь триггером БД (миграция 024) в той же транзакции, что и изменение брони. Адрес проверяется:
только https, не внутренние сети (защита от SSRF), без переходов по редиректам."""
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
from urllib.parse import urlparse

import httpx

from . import outbox
from .db import all_, run, tx
from .errors import ApiError

log = logging.getLogger("fligel.webhooks")
EVENTS = ("booking.created", "booking.updated", "booking.cancelled")
MAX_ATTEMPTS = 8
ALLOW_HTTP = os.environ.get("WEBHOOK_ALLOW_HTTP", "0") == "1"   # только для разработки: http и локальные адреса


def resolve_host(host: str) -> list[str]:
    try:
        return sorted({i[4][0] for i in socket.getaddrinfo(host, None)})
    except OSError:
        return []


def check_url(url: str) -> str:
    """Проверка адреса вебхука: https, публичный хост. Возвращает нормализованный адрес или поднимает понятную ошибку."""
    url = (url or "").strip()
    u = urlparse(url)
    if u.scheme not in (("https", "http") if ALLOW_HTTP else ("https",)) or not u.hostname:
        raise ApiError(422, "Адрес вебхука: нужен https://…", {"field": "url"})
    if u.username or u.password:
        raise ApiError(422, "Адрес вебхука не должен содержать логин и пароль", {"field": "url"})
    if len(url) > 500:
        raise ApiError(422, "Слишком длинный адрес", {"field": "url"})
    if not ALLOW_HTTP:
        ips = resolve_host(u.hostname)
        if not ips:
            raise ApiError(422, "Не удалось определить адрес сервера — проверьте имя хоста", {"field": "url"})
        for ip in ips:
            a = ipaddress.ip_address(ip)
            if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified:
                raise ApiError(422, "Адрес указывает на внутреннюю сеть — укажите публичный адрес вашего сервера", {"field": "url"})
    return url


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _default_send(url: str, body: bytes, headers: dict) -> None:
    resp = httpx.post(url, content=body, headers=headers, timeout=8, follow_redirects=False)
    if not 200 <= resp.status_code < 300:
        raise RuntimeError(f"Сервер ответил кодом {resp.status_code}")


send = _default_send  # в тестах подменяется


def process_outbox(limit: int = 20) -> dict:
    """Доставка вебхуков. Транзакция не держится во время HTTP-запроса: захват → отправка → отметка (см. app/outbox.py)."""
    outbox.recover("webhook_deliveries")
    rows = outbox.claim("webhook_deliveries",
                        "SELECT d.id, d.event, d.payload, d.attempts, d.webhook_id, w.url, w.secret, w.enabled FROM webhook_deliveries d"
                        " JOIN webhooks w ON w.id = d.webhook_id WHERE d.status = 'pending' AND d.next_attempt_at <= now()"
                        " ORDER BY d.created_at LIMIT %s FOR UPDATE OF d SKIP LOCKED", (limit,))
    sent = failed = 0
    for r in rows:
        body = json.dumps({**r["payload"], "id": str(r["id"])}, ensure_ascii=False, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "Fligel-Webhooks/1", "X-Fligel-Event": r["event"],
                   "X-Fligel-Delivery": str(r["id"]), "X-Fligel-Signature": sign(r["secret"], body)}
        try:
            if not r["enabled"]:
                raise RuntimeError("Вебхук выключен")
            check_url(r["url"])   # адрес мог начать указывать на внутреннюю сеть уже после регистрации
            send(r["url"], body, headers)
        except Exception as e:  # noqa: BLE001
            msg = (e.message if isinstance(e, ApiError) else str(e))[:300]
            with tx() as conn:
                run(conn, "UPDATE webhooks SET last_status = %s, last_delivery_at = now() WHERE id = %s", (f"ошибка: {msg}", r["webhook_id"]))
            if outbox.mark_retry("webhook_deliveries", r, msg, MAX_ATTEMPTS, give_up=not r["enabled"]):
                failed += 1
            continue
        outbox.mark_sent("webhook_deliveries", r["id"])
        with tx() as conn:
            run(conn, "UPDATE webhooks SET last_status = 'ok', last_delivery_at = now() WHERE id = %s", (r["webhook_id"],))
        sent += 1
    return {"sent": sent, "failed": failed}
