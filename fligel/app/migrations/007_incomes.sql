-- Прочие доходы (не от проживания): завтраки, парковка, доп. услуги, штрафы и т.п.
-- Устроены так же, как расходы: свои категории, привязка к объекту или к конкретному номеру
-- (либо общий доход на весь аккаунт), попадают в отчёты и в прибыль.

CREATE TABLE income_categories (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name        text NOT NULL,
    color       text NOT NULL DEFAULT '#2F5D50',
    sort_order  int NOT NULL DEFAULT 0,
    archived    boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX income_categories_account_idx ON income_categories (account_id);
CREATE UNIQUE INDEX income_categories_name_uq ON income_categories (account_id, lower(name)) WHERE NOT archived;

CREATE TABLE incomes (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    -- NULL = общий доход по всем объектам аккаунта (делится пропорционально числу номеров в отчётах).
    property_id  uuid REFERENCES properties(id) ON DELETE CASCADE,
    room_id      uuid REFERENCES rooms(id) ON DELETE CASCADE,
    category_id  uuid NOT NULL REFERENCES income_categories(id) ON DELETE RESTRICT,
    date         date NOT NULL,
    amount       numeric(12, 2) NOT NULL CHECK (amount >= 0),
    comment      text NOT NULL DEFAULT '',
    created_by   uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (room_id IS NULL OR property_id IS NOT NULL)
);
CREATE INDEX incomes_account_date_idx ON incomes (account_id, date);
CREATE INDEX incomes_property_date_idx ON incomes (property_id, date) WHERE property_id IS NOT NULL;
CREATE INDEX incomes_room_idx ON incomes (room_id) WHERE room_id IS NOT NULL;
CREATE INDEX incomes_category_idx ON incomes (category_id);

-- Расходы по номерам считаются в отчётах отдельно — нужен быстрый поиск по номеру.
CREATE INDEX expenses_room_idx ON expenses (room_id) WHERE room_id IS NOT NULL;

-- Стандартные категории доходов для аккаунтов, существовавших до этой миграции
-- (для новых их создаёт регистрация: app/expenses.py, DEFAULT_INCOME_CATEGORIES).
INSERT INTO income_categories (account_id, name, color, sort_order)
SELECT a.id, c.name, c.color, c.sort_order
FROM accounts a CROSS JOIN (VALUES
    ('Завтраки и питание', '#B7791F', 0),
    ('Дополнительные услуги', '#23767E', 1),
    ('Парковка', '#4A5A6A', 2),
    ('Трансфер', '#6E4A93', 3),
    ('Штрафы и компенсации', '#B4562E', 4),
    ('Прочее', '#69755F', 5)
) AS c(name, color, sort_order)
ON CONFLICT (account_id, lower(name)) WHERE NOT archived DO NOTHING;
