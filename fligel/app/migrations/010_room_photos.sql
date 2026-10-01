-- Фото категорий номеров для страницы бронирования. Хранятся прямо в базе (сжатые в браузере до ~1600 px):
-- никаких отдельных папок и томов, всё попадает в резервную копию вместе с остальными данными.
CREATE TABLE room_photos (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_type_id  uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    position      int NOT NULL DEFAULT 0,
    content_type  text NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp')),
    data          bytea NOT NULL,
    size          int NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX room_photos_type_idx ON room_photos (room_type_id, position);
