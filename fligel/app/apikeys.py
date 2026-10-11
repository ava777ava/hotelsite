"""Ключи публичного API: показываются один раз при создании, в базе хранится только хэш."""
import hashlib
import secrets

from .db import one, run, tx
from .errors import ApiError

PREFIX = "flg_"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create(conn, account_id, name: str, scope: str, user_id=None) -> dict:
    raw = PREFIX + secrets.token_urlsafe(30)
    row = one(conn, "INSERT INTO api_keys (account_id, name, prefix, key_hash, scope, created_by) VALUES (%s, %s, %s, %s, %s, %s)"
                    " RETURNING id, name, prefix, scope, created_at", (account_id, name, raw[:10], _hash(raw), scope, user_id))
    return {**row, "key": raw}


def authenticate(header: str) -> dict:
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "Нужен ключ API: заголовок Authorization: Bearer flg_…")
    raw = header[7:].strip()
    if not raw.startswith(PREFIX):
        raise ApiError(401, "Неверный ключ API")
    with tx() as conn:
        row = one(conn, "SELECT k.id, k.account_id, k.scope, k.last_used_at, a.status, a.is_demo FROM api_keys k JOIN accounts a ON a.id = k.account_id"
                        " WHERE k.key_hash = %s AND k.revoked_at IS NULL", (_hash(raw),))
        if not row:
            raise ApiError(401, "Неверный или отозванный ключ API")
        if row["status"] != "active" or row["is_demo"]:
            raise ApiError(403, "Аккаунт приостановлен или это демо-версия")
        if row["last_used_at"] is None or one(conn, "SELECT %s < now() - interval '1 minute' AS old", (row["last_used_at"],))["old"]:
            run(conn, "UPDATE api_keys SET last_used_at = now() WHERE id = %s", (row["id"],))
    return row
