-- Деньги в брони: история платежей, дополнительные услуги, скидка с причиной, залог.
-- bookings.paid_amount остаётся как «кэш» суммы платежей (чтобы не ломать отчёты и списки).

ALTER TABLE bookings
    ADD COLUMN discount_amount numeric(12, 2) NOT NULL DEFAULT 0,
    ADD COLUMN discount_reason text NOT NULL DEFAULT '',
    ADD COLUMN deposit_amount  numeric(12, 2) NOT NULL DEFAULT 0,
    ADD COLUMN deposit_status  text NOT NULL DEFAULT 'none'
        CHECK (deposit_status IN ('none', 'expected', 'held', 'returned', 'kept'));

CREATE TABLE booking_payments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    booking_id  uuid NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    kind        text NOT NULL DEFAULT 'payment' CHECK (kind IN ('payment', 'refund')),
    amount      numeric(12, 2) NOT NULL CHECK (amount > 0),
    method      text NOT NULL DEFAULT 'cash' CHECK (method IN ('cash', 'card', 'transfer', 'online', 'other')),
    paid_on     date NOT NULL DEFAULT current_date,
    note        text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX booking_payments_booking_idx ON booking_payments (booking_id, paid_on);
CREATE INDEX booking_payments_account_idx ON booking_payments (account_id, paid_on);

-- Справочник дополнительных услуг (завтрак, трансфер, поздний выезд…)
CREATE TABLE services (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name        text NOT NULL,
    price       numeric(12, 2) NOT NULL DEFAULT 0 CHECK (price >= 0),
    active      boolean NOT NULL DEFAULT true,
    sort_order  int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX services_account_idx ON services (account_id);

-- Услуги в конкретной брони: название и цена копируются, чтобы изменение справочника не меняло старые счета
CREATE TABLE booking_services (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    booking_id  uuid NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    service_id  uuid REFERENCES services(id) ON DELETE SET NULL,
    name        text NOT NULL,
    price       numeric(12, 2) NOT NULL CHECK (price >= 0),
    qty         int NOT NULL DEFAULT 1 CHECK (qty > 0),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX booking_services_booking_idx ON booking_services (booking_id);

-- Уже внесённые оплаты превращаем в записи истории платежей
INSERT INTO booking_payments (account_id, booking_id, kind, amount, method, paid_on, note)
SELECT account_id, id, 'payment', paid_amount, 'other', created_at::date, 'Перенесено из прежнего поля «Оплачено»'
FROM bookings WHERE paid_amount > 0;
