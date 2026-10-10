-- Шахматка: групповая бронь (несколько номеров одному гостю / переселение) и заметки на даты.

ALTER TABLE bookings ADD COLUMN group_id uuid;
CREATE INDEX bookings_group_idx ON bookings (group_id) WHERE group_id IS NOT NULL;

CREATE TABLE date_notes (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    day          date NOT NULL,
    text         text NOT NULL,
    user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (property_id, day)
);
CREATE INDEX date_notes_account_idx ON date_notes (account_id);
