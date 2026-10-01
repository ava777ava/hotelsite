"""Фото категорий номеров: загрузка (владелец), порядок, удаление и публичная отдача для страницы гостей."""
import base64
import binascii

from starlette.responses import Response
from starlette.routing import Route

from ..db import all_, one, run, tx
from ..errors import ApiError
from ..util import parse_uuid
from .base import Ctx, api

MAX_PHOTOS_PER_TYPE = 8
MAX_PHOTO_BYTES = 2 * 1024 * 1024  # браузер сжимает до ~300 КБ; 2 МБ — потолок на случай обхода


def sniff(data: bytes) -> str | None:
    """Тип по содержимому, а не по тому, что заявил клиент. SVG намеренно не принимаем: в нём бывают скрипты."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@api("manager")
def list_photos(c: Ctx):
    tid = parse_uuid(c.path["id"], "Категория")
    with tx() as conn:
        if not one(conn, "SELECT 1 FROM room_types WHERE id = %s AND account_id = %s", (tid, c.account_id)):
            raise ApiError(404, "Категория не найдена")
        return all_(conn, "SELECT id, position, size FROM room_photos WHERE room_type_id = %s AND account_id = %s"
                          " ORDER BY position, created_at", (tid, c.account_id))


@api("owner")
def upload_photo(c: Ctx):
    tid = parse_uuid(c.path["id"], "Категория")
    raw = str(c.data.get("data") or "")
    if "," in raw[:100]:  # допускаем data-URL вида data:image/jpeg;base64,....
        raw = raw.split(",", 1)[1]
    if len(raw) > MAX_PHOTO_BYTES * 4 // 3 + 16:
        raise ApiError(413, "Фото слишком большое (больше 2 МБ)")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError(422, "Не удалось прочитать фото")
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise ApiError(413, "Фото слишком большое (больше 2 МБ)")
    ctype = sniff(data)
    if not ctype:
        raise ApiError(422, "Подходят только фото JPEG, PNG или WebP")
    with tx() as conn:
        if not one(conn, "SELECT 1 FROM room_types WHERE id = %s AND account_id = %s FOR UPDATE", (tid, c.account_id)):
            raise ApiError(404, "Категория не найдена")
        if one(conn, "SELECT count(*) AS n FROM room_photos WHERE room_type_id = %s", (tid,))["n"] >= MAX_PHOTOS_PER_TYPE:
            raise ApiError(422, f"Не больше {MAX_PHOTOS_PER_TYPE} фото на категорию")
        return one(conn, "INSERT INTO room_photos (account_id, room_type_id, position, content_type, data, size)"
                         " VALUES (%s, %s, (SELECT coalesce(max(position), -1) + 1 FROM room_photos WHERE room_type_id = %s),"
                         " %s, %s, %s) RETURNING id, position, size", (c.account_id, tid, tid, ctype, data, len(data)))


@api("owner")
def reorder_photos(c: Ctx):
    tid = parse_uuid(c.path["id"], "Категория")
    ids = c.data.get("ids")
    if not isinstance(ids, list):
        raise ApiError(422, "Нужен список фото")
    ids = [parse_uuid(i, "Фото") for i in ids]
    with tx() as conn:
        have = {str(r["id"]) for r in all_(conn, "SELECT id FROM room_photos WHERE room_type_id = %s AND account_id = %s",
                                            (tid, c.account_id))}
        if set(ids) != have:
            raise ApiError(422, "Список фото не совпадает с загруженными")
        for pos, pid in enumerate(ids):
            run(conn, "UPDATE room_photos SET position = %s WHERE id = %s AND account_id = %s", (pos, pid, c.account_id))


@api("owner")
def delete_photo(c: Ctx):
    with tx() as conn:
        if not run(conn, "DELETE FROM room_photos WHERE id = %s AND account_id = %s",
                   (parse_uuid(c.path["id"], "Фото"), c.account_id)):
            raise ApiError(404, "Фото не найдено")


@api("manager")
def photo_file(c: Ctx):
    """Файл фото для администратора (миниатюры в настройках) — работает и при выключенном бронировании."""
    with tx() as conn:
        row = one(conn, "SELECT content_type, data FROM room_photos WHERE id = %s AND account_id = %s",
                  (parse_uuid(c.path["id"], "Фото"), c.account_id))
    if not row:
        raise ApiError(404, "Фото не найдено")
    return Response(bytes(row["data"]), media_type=row["content_type"], headers={"Cache-Control": "private, max-age=3600"})


@api(public=True)
def serve_photo(c: Ctx):
    """Публичная отдача: адрес с неугадываемым id; фото отдаётся, только если у объекта включено
    бронирование и аккаунт активен (иначе закрытый объект не светил бы свои фото)."""
    with tx() as conn:
        row = one(conn, "SELECT ph.content_type, ph.data FROM room_photos ph"
                        " JOIN room_types rt ON rt.id = ph.room_type_id"
                        " JOIN properties p ON p.id = rt.property_id AND p.booking_enabled"
                        " JOIN accounts a ON a.id = ph.account_id AND a.status = 'active'"
                        " WHERE ph.id = %s", (parse_uuid(c.path["id"], "Фото"),))
    if not row:
        raise ApiError(404, "Фото не найдено")
    return Response(bytes(row["data"]), media_type=row["content_type"], headers={
        "Cache-Control": "public, max-age=604800, immutable", "X-Content-Type-Options": "nosniff"})


routes = [
    Route("/api/room-types/{id}/photos", list_photos),
    Route("/api/room-types/{id}/photos", upload_photo, methods=["POST"]),
    Route("/api/room-types/{id}/photos/order", reorder_photos, methods=["PUT"]),
    Route("/api/photos/{id}", delete_photo, methods=["DELETE"]),
    Route("/api/photos/{id}/file", photo_file),
    Route("/media/photo/{id}", serve_photo),
]
