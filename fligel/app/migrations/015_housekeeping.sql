-- Уборка: статус номера, заметки, назначение горничной. Таблица rooms уже содержит cleaned_on (миграция 008).

ALTER TABLE rooms
    ADD COLUMN hk_status      text NOT NULL DEFAULT 'clean' CHECK (hk_status IN ('clean', 'dirty', 'cleaning', 'inspect', 'repair')),
    ADD COLUMN hk_note        text NOT NULL DEFAULT '',   -- причина статуса (что сломалось и т. п.)
    ADD COLUMN hk_updated_at  timestamptz,
    ADD COLUMN hk_assigned_to uuid REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN hk_assigned_on date,                       -- назначение действует в этот день
    ADD COLUMN note           text NOT NULL DEFAULT '';   -- постоянная заметка к номеру (ключ у соседей, диван раскладывается…)

CREATE TABLE room_status_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_id     uuid NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    status      text NOT NULL,
    note        text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX room_status_log_room_idx ON room_status_log (room_id, created_at DESC);
