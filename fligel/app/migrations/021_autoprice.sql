-- Автоцены: правила (низкая загрузка, выходные, праздники, последний свободный номер), предложения, журнал изменений цен.

ALTER TABLE room_types
    ADD COLUMN min_price numeric(12, 2) CHECK (min_price IS NULL OR min_price >= 0),   -- автоцены не опускаются ниже
    ADD COLUMN max_price numeric(12, 2) CHECK (max_price IS NULL OR max_price >= 0);  -- и не поднимаются выше

CREATE TABLE price_settings (
    account_id  uuid PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    mode        text NOT NULL DEFAULT 'off' CHECK (mode IN ('off', 'suggest', 'auto')),   -- выключено / только предлагать / применять самому
    horizon_days int NOT NULL DEFAULT 60 CHECK (horizon_days BETWEEN 7 AND 180),
    last_run_on date,                                   -- раз в день планировщик пересчитывает
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE price_rules (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind         text NOT NULL CHECK (kind IN ('low_occupancy', 'weekend', 'holiday', 'last_room')),
    room_type_id uuid REFERENCES room_types(id) ON DELETE CASCADE,   -- NULL = все категории
    days_ahead   int NOT NULL DEFAULT 14 CHECK (days_ahead BETWEEN 0 AND 180),        -- low_occupancy: ближайшие N дней
    threshold    int NOT NULL DEFAULT 40 CHECK (threshold BETWEEN 1 AND 100),         -- low_occupancy: загрузка категории ниже X %
    percent      numeric(5, 1) NOT NULL CHECK (percent BETWEEN -90 AND 300),          -- на сколько % менять цену (минус — скидка)
    enabled      boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX price_rules_account_idx ON price_rules (account_id);

CREATE TABLE price_suggestions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_type_id    uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    date            date NOT NULL,
    current_price   numeric(12, 2) NOT NULL,
    suggested_price numeric(12, 2) NOT NULL,
    base_price      numeric(12, 2),
    reasons         text NOT NULL DEFAULT '',
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'dismissed')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    decided_at      timestamptz,
    decided_by      uuid REFERENCES users(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX price_suggestions_pending_uq ON price_suggestions (room_type_id, date) WHERE status = 'pending';
CREATE INDEX price_suggestions_account_idx ON price_suggestions (account_id, status, date);

CREATE TABLE price_changes (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_type_id uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    date         date NOT NULL,
    old_price    numeric(12, 2),
    new_price    numeric(12, 2) NOT NULL,
    base_price   numeric(12, 2),            -- от какой цены считали (ручная цена или базовая категории)
    reasons      text NOT NULL DEFAULT '',
    source       text NOT NULL CHECK (source IN ('auto', 'suggestion')),
    user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX price_changes_account_idx ON price_changes (account_id, created_at DESC);
CREATE INDEX price_changes_type_date_idx ON price_changes (room_type_id, date, created_at DESC);
