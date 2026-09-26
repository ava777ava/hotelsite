"""Общие мелочи для нескольких API-модулей."""
from ..db import one
from ..errors import ApiError
from ..util import parse_uuid


def selected_property(conn, account_id: str, property_id) -> dict:
    """Выбранный объект: по property_id, если передан и принадлежит аккаунту,
    иначе первый объект аккаунта по дате создания (для обратной совместимости)."""
    if property_id:
        prop = one(conn, "SELECT * FROM properties WHERE id = %s AND account_id = %s",
                   (parse_uuid(property_id, "Объект"), account_id))
        if not prop:
            raise ApiError(404, "Объект не найден")
        return prop
    prop = one(conn, "SELECT * FROM properties WHERE account_id = %s ORDER BY created_at LIMIT 1", (account_id,))
    if not prop:
        raise ApiError(404, "Объект не найден")
    return prop
