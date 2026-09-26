-- Расходы: категории, сами расходы и шаблоны повторяющихся расходов.

CREATE TABLE expense_categories (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name        text NOT NULL,
    color       text NOT NULL DEFAULT '#69755F',
    sort_order  int NOT NULL DEFAULT 0,
    archived    boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX expense_categories_account_idx ON expense_categories (account_id);
-- Имя уникально среди активных категорий аккаунта; в архиве может лежать «Прочее» под старым именем.
CREATE UNIQUE INDEX expense_categories_name_uq ON expense_categories (account_id, lower(name)) WHERE NOT archived;

-- Шаблон повторяющегося расхода: «каждый месяц N-го числа» (аренда, интернет, зарплата).
-- День месяца ограничен 28-м, чтобы дата гарантированно существовала в любом месяце.
CREATE TABLE expense_recurring_rules (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    property_id  uuid REFERENCES properties(id) ON DELETE CASCADE,
    room_id      uuid REFERENCES rooms(id) ON DELETE CASCADE,
    category_id  uuid NOT NULL REFERENCES expense_categories(id) ON DELETE RESTRICT,
    amount       numeric(12, 2) NOT NULL CHECK (amount >= 0),
    day_of_month int NOT NULL CHECK (day_of_month BETWEEN 1 AND 28),
    comment      text NOT NULL DEFAULT '',
    active       boolean NOT NULL DEFAULT true,
    created_by   uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (room_id IS NULL OR property_id IS NOT NULL)
);
CREATE INDEX expense_recurring_rules_account_idx ON expense_recurring_rules (account_id) WHERE active;

CREATE TABLE expenses (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id        uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    -- NULL = общий расход по всем объектам аккаунта (делится пропорционально числу номеров в отчётах).
    property_id       uuid REFERENCES properties(id) ON DELETE CASCADE,
    room_id           uuid REFERENCES rooms(id) ON DELETE CASCADE,
    category_id       uuid NOT NULL REFERENCES expense_categories(id) ON DELETE RESTRICT,
    date              date NOT NULL,
    amount            numeric(12, 2) NOT NULL CHECK (amount >= 0),
    comment           text NOT NULL DEFAULT '',
    created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
    recurring_rule_id uuid REFERENCES expense_recurring_rules(id) ON DELETE SET NULL,
    recurring_period  text,  -- 'YYYY-MM' — только у расходов, созданных по шаблону; защита от дублей
    created_at        timestamptz NOT NULL DEFAULT now(),
    CHECK (room_id IS NULL OR property_id IS NOT NULL)
);
CREATE INDEX expenses_account_date_idx ON expenses (account_id, date);
CREATE INDEX expenses_property_idx ON expenses (property_id) WHERE property_id IS NOT NULL;
CREATE INDEX expenses_category_idx ON expenses (category_id);
CREATE UNIQUE INDEX expenses_recurring_period_uq ON expenses (recurring_rule_id, recurring_period)
    WHERE recurring_rule_id IS NOT NULL;

-- Стандартные категории для аккаунтов, уже существующих на момент миграции.
-- Для новых аккаунтов их создаёт регистрация (app/api/account.py, DEFAULT_EXPENSE_CATEGORIES).
INSERT INTO expense_categories (account_id, name, color, sort_order)
SELECT a.id, c.name, c.color, c.sort_order
FROM accounts a CROSS JOIN (VALUES
    ('Уборка и прачечная', '#23767E', 0),
    ('Коммунальные услуги', '#4A5A6A', 1),
    ('Комиссии площадок', '#6E4A93', 2),
    ('Ремонт и обслуживание', '#B4562E', 3),
    ('Расходники', '#B7791F', 4),
    ('Зарплата', '#2F5D50', 5),
    ('Аренда/ипотека', '#5E6B5A', 6),
    ('Налоги', '#7A3418', 7),
    ('Реклама', '#8A5A12', 8),
    ('Прочее', '#69755F', 9)
) AS c(name, color, sort_order)
ON CONFLICT (account_id, lower(name)) WHERE NOT archived DO NOTHING;
