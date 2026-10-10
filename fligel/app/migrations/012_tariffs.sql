-- Тарифы (невозвратный, с завтраком…), доплата за гостей сверх включённых, скидка за длительность.

ALTER TABLE room_types
    ADD COLUMN included_guests        int NOT NULL DEFAULT 0 CHECK (included_guests >= 0),   -- 0 = вся вместимость включена
    ADD COLUMN extra_guest_price      numeric(12, 2) NOT NULL DEFAULT 0 CHECK (extra_guest_price >= 0),
    ADD COLUMN week_discount_percent  numeric(5, 2) NOT NULL DEFAULT 0 CHECK (week_discount_percent BETWEEN 0 AND 90),
    ADD COLUMN month_discount_percent numeric(5, 2) NOT NULL DEFAULT 0 CHECK (month_discount_percent BETWEEN 0 AND 90);

CREATE TABLE rate_plans (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_type_id  uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    name          text NOT NULL,
    description   text NOT NULL DEFAULT '',
    percent_delta numeric(6, 2) NOT NULL DEFAULT 0 CHECK (percent_delta BETWEEN -90 AND 300),  -- ±% к цене ночи
    fixed_delta   numeric(12, 2) NOT NULL DEFAULT 0,                                            -- ± ₽ за ночь
    refundable    boolean NOT NULL DEFAULT true,
    breakfast     boolean NOT NULL DEFAULT false,
    active        boolean NOT NULL DEFAULT true,
    sort_order    int NOT NULL DEFAULT 0,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX rate_plans_type_idx ON rate_plans (room_type_id);
CREATE INDEX rate_plans_account_idx ON rate_plans (account_id);

ALTER TABLE bookings
    ADD COLUMN rate_plan_id   uuid REFERENCES rate_plans(id) ON DELETE SET NULL,
    ADD COLUMN rate_plan_name text NOT NULL DEFAULT '';
