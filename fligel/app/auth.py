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

# «Собственник» ниже всех: обычные разделы ему закрыты, у него только свои отчёты (api/owners.py)
ROLES_ORDER = {"landlord": -1, "housekeeper": 0, "manager": 1, "owner": 2}


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
    iat: int = 0

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
    if data.get("kind") or "acc" not in data:  # токен оператора (или чужой формы) для обычного API не годится
        raise ApiError(401, "Нужно войти в систему")
    p = Principal(user_id=data["sub"], account_id=data["acc"], role=data["role"], iat=int(data.get("iat") or 0))
    p.require(min_role)
    return p


def verify_active(conn, p: Principal) -> None:
    """Токен подписан верно и не истёк, но это не значит, что им ещё можно пользоваться:
    сотрудника могли удалить, а аккаунт — приостановить уже после того, как токен выдан.
    Проверяем это на каждый запрос (не только при входе), иначе доступ можно отозвать
    только сменой SECRET_KEY — сразу у всех клиентов сразу."""
    row = one(conn, "SELECT a.status, u.sessions_valid_from FROM users u JOIN accounts a ON a.id = u.account_id"
                    " WHERE u.id = %s AND u.account_id = %s", (p.user_id, p.account_id))
    if not row:
        raise ApiError(401, "Нужно войти в систему")
    if p.iat < int(row["sessions_valid_from"].timestamp()):
        raise ApiError(401, "Пароль был изменён — войдите заново")
    if row["status"] != "active":
        raise ApiError(403, "Аккаунт приостановлен. Свяжитесь с поддержкой")


def new_ical_token() -> str:
    return secrets.token_urlsafe(18)


def new_reset_token() -> str:
    return secrets.token_urlsafe(32)


def make_operator_token(operator_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(operator_id), "kind": "operator", "iat": now, "exp": now + timedelta(hours=12)}, config.SECRET_KEY, algorithm="HS256")


def operator_from_request(request: Request) -> str:
    """Id оператора по токену панели оператора. Токены клиентов сюда не проходят (у них нет kind=operator)."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "Нужно войти в панель оператора")
    try:
        data = jwt.decode(header[7:], config.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise ApiError(401, "Нужно войти в панель оператора")
    if data.get("kind") != "operator":
        raise ApiError(401, "Нужно войти в панель оператора")
    return data["sub"]
