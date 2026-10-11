-- Автопилот: сценарии «событие → условие → действие», задачи команды, анкета гостя перед приездом,
-- код двери/сейфа, отзывы после выезда. Паспортные данные гостей не собираются (152-ФЗ) — только имя, телефон, email, пожелания.

ALTER TABLE bookings ADD COLUMN door_code text NOT NULL DEFAULT '';   -- код двери/сейфа для этой брони
ALTER TABLE rooms    ADD COLUMN door_code text NOT NULL DEFAULT '';   -- постоянный код номера (если у брони свой — используется он)

-- Задачи команды ("заменить лампочку", "принять бельё"), в том числе повторяющиеся
CREATE TABLE tasks (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id        uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    title             text NOT NULL,
    description       text NOT NULL DEFAULT '',
    property_id       uuid REFERENCES properties(id) ON DELETE SET NULL,
    room_id           uuid REFERENCES rooms(id) ON DELETE SET NULL,
    booking_id        uuid REFERENCES bookings(id) ON DELETE SET NULL,
    assignee_id       uuid REFERENCES users(id) ON DELETE SET NULL,
    due_date          date,
    recurrence        text NOT NULL DEFAULT 'none' CHECK (recurrence IN ('none', 'weekly', 'monthly')),
    source            text NOT NULL DEFAULT 'manual',        -- manual | automation | inventory | stock | meter
    done_at           timestamptz,
    done_by           uuid REFERENCES users(id) ON DELETE SET NULL,
    overdue_notified_on date,                                -- чтобы напомнить о просрочке не чаще раза в день
    created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tasks_account_open_idx ON tasks (account_id, due_date) WHERE done_at IS NULL;
CREATE INDEX tasks_assignee_idx ON tasks (assignee_id) WHERE done_at IS NULL;

-- Правила автопилота
CREATE TABLE automation_rules (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    preset       text,                                       -- ключ готового сценария (NULL — своё правило)
    name         text NOT NULL,
    event        text NOT NULL CHECK (event IN ('before_checkin', 'checkin_day', 'checkout_day', 'after_checkout', 'new_booking', 'debt')),
    offset_days  int NOT NULL DEFAULT 0 CHECK (offset_days BETWEEN 0 AND 60),
    at_hour      int NOT NULL DEFAULT 10 CHECK (at_hour BETWEEN 0 AND 23),   -- не раньше этого часа (по времени сервера)
    only_unpaid  boolean NOT NULL DEFAULT false,             -- условие: по брони есть долг
    sources      text[] NOT NULL DEFAULT '{}',               -- условие: только эти источники (пусто = любые)
    property_id  uuid REFERENCES properties(id) ON DELETE CASCADE,          -- условие: только этот объект
    action       text NOT NULL CHECK (action IN ('notify_staff', 'email_guest', 'create_task', 'set_cleaning')),
    params       jsonb NOT NULL DEFAULT '{}',
    enabled      boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX automation_rules_account_idx ON automation_rules (account_id);
CREATE UNIQUE INDEX automation_rules_preset_uq ON automation_rules (account_id, preset) WHERE preset IS NOT NULL;

-- Журнал срабатываний; уникальность (правило, бронь) = каждое правило срабатывает по брони не больше одного раза
CREATE TABLE automation_runs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    rule_id     uuid NOT NULL REFERENCES automation_rules(id) ON DELETE CASCADE,
    booking_id  uuid NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    status      text NOT NULL DEFAULT 'done' CHECK (status IN ('done', 'skipped', 'error')),
    detail      text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rule_id, booking_id)
);
CREATE INDEX automation_runs_account_idx ON automation_runs (account_id, created_at DESC);

-- Анкета гостя перед приездом (по секретной ссылке, без входа)
CREATE TABLE booking_forms (
    booking_id    uuid PRIMARY KEY REFERENCES bookings(id) ON DELETE CASCADE,
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token         text NOT NULL UNIQUE,
    arrival_time  text NOT NULL DEFAULT '',
    guests_count  int,
    wishes        text NOT NULL DEFAULT '',
    car_number    text NOT NULL DEFAULT '',
    filled_at     timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX booking_forms_account_idx ON booking_forms (account_id);

-- Отзыв гостя после выезда (по секретной ссылке): оценка 1–5 и комментарий, только для внутренней статистики
CREATE TABLE reviews (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    booking_id    uuid NOT NULL UNIQUE REFERENCES bookings(id) ON DELETE CASCADE,
    property_id   uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    room_id       uuid NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    token         text NOT NULL UNIQUE,
    rating        int CHECK (rating BETWEEN 1 AND 5),
    comment       text NOT NULL DEFAULT '',
    submitted_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX reviews_account_idx ON reviews (account_id, submitted_at DESC);

-- Новые события для мессенджеров (автопилот, задачи, отзывы): добавляем тем, кто уже настроил подписки
UPDATE telegram_links SET events = ARRAY(SELECT DISTINCT unnest(events || ARRAY['automation', 'task', 'review']));
UPDATE max_links SET events = ARRAY(SELECT DISTINCT unnest(events || ARRAY['automation', 'task', 'review']));
ALTER TABLE telegram_links ALTER COLUMN events SET DEFAULT ARRAY['new_booking', 'cancellation', 'conflict', 'sync_error', 'digest', 'room_issue', 'automation', 'task', 'review'];
ALTER TABLE max_links ALTER COLUMN events SET DEFAULT ARRAY['new_booking', 'cancellation', 'conflict', 'sync_error', 'digest', 'room_issue', 'automation', 'task', 'review'];
