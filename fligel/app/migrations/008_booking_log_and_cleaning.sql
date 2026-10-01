-- История изменений брони: кто и когда создал, поменял даты/цену/номер/статус, отменил.
CREATE TABLE booking_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    booking_id  uuid NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,   -- NULL = система (синхронизация площадки)
    action      text NOT NULL,                                  -- created / updated / cancelled
    details     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX booking_log_booking_idx ON booking_log (booking_id, created_at DESC);
CREATE INDEX booking_log_account_idx ON booking_log (account_id, created_at DESC);

-- Уборка: дата, когда номер последний раз отметили убранным. Номер, из которого сегодня выезжают,
-- «ждёт уборки», пока cleaned_on не станет сегодняшней датой.
ALTER TABLE rooms ADD COLUMN cleaned_on date;
