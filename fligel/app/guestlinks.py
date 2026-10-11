"""Секретные ссылки для гостя без входа в систему: анкета перед приездом (/f/<токен>) и отзыв после выезда (/r/<токен>).

Токен создаётся при первом обращении (ссылка нужна в письме или шаблоне) и не меняется. Угадать его нельзя (24 байта случайности)."""
import secrets

from . import config
from .db import one


def _token() -> str:
    return secrets.token_urlsafe(24)


def form_url(token: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/f/{token}"


def review_url(token: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/r/{token}"


def ensure_form(conn, account_id, booking_id) -> str:
    row = one(conn, "INSERT INTO booking_forms (booking_id, account_id, token) VALUES (%s, %s, %s)"
                    " ON CONFLICT (booking_id) DO UPDATE SET booking_id = EXCLUDED.booking_id RETURNING token",
              (booking_id, account_id, _token()))
    return row["token"]


def ensure_review(conn, booking: dict) -> str:
    row = one(conn, "INSERT INTO reviews (account_id, booking_id, property_id, room_id, token) VALUES (%s, %s, %s, %s, %s)"
                    " ON CONFLICT (booking_id) DO UPDATE SET booking_id = EXCLUDED.booking_id RETURNING token",
              (booking["account_id"], booking["id"], booking["property_id"], booking["room_id"], _token()))
    return row["token"]
