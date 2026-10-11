-- Хозяйство: склад расходников, счётчики (вода/свет) с автоматическим расходом, инвентарь номеров и проверка после выезда.

-- ---------- склад расходников ----------
CREATE TABLE stock_items (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id         uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    property_id        uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    name               text NOT NULL,
    unit               text NOT NULL DEFAULT 'шт',
    quantity           numeric(12, 2) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    min_quantity       numeric(12, 2) NOT NULL DEFAULT 0 CHECK (min_quantity >= 0),     -- ниже этого — «заканчивается»
    norm_per_cleaning  numeric(12, 2) NOT NULL DEFAULT 0 CHECK (norm_per_cleaning >= 0), -- списывается при каждой уборке номера
    low_notified_on    date,                                                            -- не чаще раза в день
    archived           boolean NOT NULL DEFAULT false,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX stock_items_property_idx ON stock_items (account_id, property_id) WHERE NOT archived;

CREATE TABLE stock_moves (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    item_id     uuid NOT NULL REFERENCES stock_items(id) ON DELETE CASCADE,
    delta       numeric(12, 2) NOT NULL,                       -- + приход, − расход
    kind        text NOT NULL CHECK (kind IN ('in', 'out', 'writeoff', 'cleaning', 'correction')),
    note        text NOT NULL DEFAULT '',
    room_id     uuid REFERENCES rooms(id) ON DELETE SET NULL,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX stock_moves_item_idx ON stock_moves (item_id, created_at DESC);

-- ---------- счётчики ----------
CREATE TABLE meters (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    room_id      uuid REFERENCES rooms(id) ON DELETE CASCADE,   -- NULL = общий счётчик объекта
    kind         text NOT NULL CHECK (kind IN ('water_cold', 'water_hot', 'electricity', 'gas', 'heat')),
    name         text NOT NULL DEFAULT '',
    unit         text NOT NULL DEFAULT '',
    tariff       numeric(12, 4) NOT NULL DEFAULT 0 CHECK (tariff >= 0),   -- ₽ за единицу
    archived     boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX meters_property_idx ON meters (account_id, property_id) WHERE NOT archived;

CREATE TABLE meter_readings (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    meter_id     uuid NOT NULL REFERENCES meters(id) ON DELETE CASCADE,
    date         date NOT NULL,
    value        numeric(14, 3) NOT NULL CHECK (value >= 0),
    consumption  numeric(14, 3) NOT NULL DEFAULT 0,             -- расход с предыдущего показания
    tariff       numeric(12, 4) NOT NULL DEFAULT 0,             -- тариф на момент показания
    cost         numeric(12, 2) NOT NULL DEFAULT 0,
    expense_id   uuid REFERENCES expenses(id) ON DELETE SET NULL,   -- расход, созданный автоматически
    replaced     boolean NOT NULL DEFAULT false,                -- счётчик заменён: расход от этого показания не считается
    note         text NOT NULL DEFAULT '',
    user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX meter_readings_meter_idx ON meter_readings (meter_id, date DESC, created_at DESC);

-- ---------- инвентарь номеров и проверка после выезда ----------
CREATE TABLE inventory_items (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_id     uuid NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    name        text NOT NULL,
    qty         int NOT NULL DEFAULT 1 CHECK (qty >= 1),
    note        text NOT NULL DEFAULT '',
    sort_order  int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX inventory_items_room_idx ON inventory_items (room_id, sort_order);

CREATE TABLE inventory_checks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_id     uuid NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    booking_id  uuid REFERENCES bookings(id) ON DELETE SET NULL,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    problems    int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX inventory_checks_room_idx ON inventory_checks (room_id, created_at DESC);

CREATE TABLE inventory_check_items (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    check_id    uuid NOT NULL REFERENCES inventory_checks(id) ON DELETE CASCADE,
    name        text NOT NULL,
    qty         int NOT NULL,
    state       text NOT NULL CHECK (state IN ('ok', 'missing', 'broken')),
    note        text NOT NULL DEFAULT ''
);
CREATE INDEX inventory_check_items_check_idx ON inventory_check_items (check_id);

-- Новое событие для мессенджеров: «расходник заканчивается»
UPDATE telegram_links SET events = ARRAY(SELECT DISTINCT unnest(events || ARRAY['stock']));
UPDATE max_links SET events = ARRAY(SELECT DISTINCT unnest(events || ARRAY['stock']));
ALTER TABLE telegram_links ALTER COLUMN events SET DEFAULT ARRAY['new_booking', 'cancellation', 'conflict', 'sync_error', 'digest', 'room_issue', 'automation', 'task', 'review', 'stock'];
ALTER TABLE max_links ALTER COLUMN events SET DEFAULT ARRAY['new_booking', 'cancellation', 'conflict', 'sync_error', 'digest', 'room_issue', 'automation', 'task', 'review', 'stock'];
