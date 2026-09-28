"""Пароли (scrypt), JWT-токены и проверка прав."""
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from starlette.requests import Request

from . import config
from .db import one
from .errors import ApiError

ROLES_ORDER = {"housekeeper": 0, "manager": 1, "owner": 2}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(digest, expected)


def make_token(user_id: str, account_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "acc": str(account_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=config.TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


@dataclass
class Principal:
    user_id: str
    account_id: str
    role: str

    def require(self, min_role: str) -> None:
        if ROLES_ORDER[self.role] < ROLES_ORDER[min_role]:
            raise ApiError(403, "Недостаточно прав для этого действия")


def principal(request: Request, min_role: str = "housekeeper") -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "Нужно войти в систему")
    try:
        data = jwt.decode(header[7:], config.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "Сессия истекла, войдите заново")
    except jwt.InvalidTokenError:
        raise ApiError(401, "Нужно войти в систему")
    p = Principal(user_id=data["sub"], account_id=data["acc"], role=data["role"])
    p.require(min_role)
    return p


def verify_active(conn, p: Principal) -> None:
    """Токен подписан верно и не истёк, но это не значит, что им ещё можно пользоваться:
    сотрудника могли удалить, а аккаунт — приостановить уже после того, как токен выдан.
    Проверяем это на каждый запрос (не только при входе), иначе доступ можно отозвать
    только сменой SECRET_KEY — сразу у всех клиентов сразу."""
    row = one(conn, "SELECT a.status FROM users u JOIN accounts a ON a.id = u.account_id"
                    " WHERE u.id = %s AND u.account_id = %s", (p.user_id, p.account_id))
    if not row:
        raise ApiError(401, "Нужно войти в систему")
    if row["status"] != "active":
        raise ApiError(403, "Аккаунт приостановлен. Свяжитесь с поддержкой")


def new_ical_token() -> str:
    return secrets.token_urlsafe(18)
