-- Флигель: базовая схема.
-- Каждая бизнес-таблица содержит account_id: система мультитенантная с первого дня.

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Аккаунт = один клиент сервиса (владелец или управляющая компания)
CREATE TABLE accounts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    plan        text NOT NULL DEFAULT 'trial',
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    paid_until  date,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id     uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    email          text NOT NULL,
    password_hash  text NOT NULL,
    name           text NOT NULL,
    role           text NOT NULL CHECK (role IN ('owner', 'manager', 'housekeeper')),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_uq ON users (lower(email));
CREATE INDEX users_account_idx ON users (account_id);

-- Объект размещения (гостиница, апарт-отель, квартира)
CREATE TABLE properties (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name            text NOT NULL,
    address         text NOT NULL DEFAULT '',
    phone           text NOT NULL DEFAULT '',
    timezone        text NOT NULL DEFAULT 'Europe/Moscow',
    check_in_time   time NOT NULL DEFAULT '14:00',
    check_out_time  time NOT NULL DEFAULT '12:00',
    public_slug     text NOT NULL UNIQUE,          -- адрес страницы бронирования: /book/<slug>
    booking_enabled boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX properties_account_idx ON properties (account_id);

-- Категория номеров (Стандарт, Делюкс...). Цены задаются на категорию.
CREATE TABLE room_types (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    name         text NOT NULL,
    description  text NOT NULL DEFAULT '',
    capacity     int  NOT NULL DEFAULT 2 CHECK (capacity > 0),
    base_price   numeric(12, 2) NOT NULL DEFAULT 0 CHECK (base_price >= 0),
    min_stay     int  NOT NULL DEFAULT 1 CHECK (min_stay > 0),
    sort_order   int  NOT NULL DEFAULT 0,
    ical_token   text NOT NULL UNIQUE,             -- секрет в ссылке календаря категории
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX room_types_account_idx ON room_types (account_id);

-- Конкретный номер. Одна строка шахматки.
CREATE TABLE rooms (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    property_id   uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    room_type_id  uuid NOT NULL REFERENCES room_types(id) ON DELETE RESTRICT,
    name          text NOT NULL,
    sort_order    int  NOT NULL DEFAULT 0,
    ical_token    text NOT NULL UNIQUE,            -- секрет в ссылке экспорта календаря
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX rooms_account_idx ON rooms (account_id);

-- Внешние календари площадок (iCal). Привязка — к номеру (квартиры, Авито)
-- или к категории (гостиницы в Яндекс Путешествиях: одна ссылка на категорию).
CREATE TABLE ical_feeds (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_id         uuid REFERENCES rooms(id) ON DELETE CASCADE,
    room_type_id    uuid REFERENCES room_types(id) ON DELETE CASCADE,
    channel         text NOT NULL CHECK (channel IN ('avito', 'yandex', 'sutochno', 'ostrovok', 'other')),
    url             text NOT NULL,
    enabled         boolean NOT NULL DEFAULT true,
    last_synced_at  timestamptz,
    last_status     text,                          -- ok / error
    last_error      text,
    next_run_at     timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((room_id IS NULL) <> (room_type_id IS NULL))
);
CREATE UNIQUE INDEX ical_feeds_room_uq ON ical_feeds (room_id, channel) WHERE room_id IS NOT NULL;
CREATE UNIQUE INDEX ical_feeds_type_uq ON ical_feeds (room_type_id, channel) WHERE room_type_id IS NOT NULL;

-- Как отдавать календарь категории площадке:
--   per_booking — каждая бронь отдельным событием (площадка вычитает по номеру на событие);
--   sold_out    — занятыми отдаются только даты, когда свободных номеров в категории нет.
CREATE TABLE ical_export_settings (
    room_type_id  uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    channel       text NOT NULL,
    mode          text NOT NULL DEFAULT 'per_booking' CHECK (mode IN ('per_booking', 'sold_out')),
    PRIMARY KEY (room_type_id, channel)
);
CREATE INDEX ical_feeds_due_idx ON ical_feeds (next_run_at) WHERE enabled;

-- Когда площадка последний раз забирала наш календарь (номера или категории).
-- Нужно, чтобы отличать «эхо» (наша же бронь, вернувшаяся из календаря площадки)
-- от настоящего двойного бронирования.
CREATE TABLE ical_exports (
    target_id        uuid NOT NULL,                -- id номера или категории
    channel          text NOT NULL,
    last_fetched_at  timestamptz NOT NULL DEFAULT now(),
    fetch_count      bigint NOT NULL DEFAULT 1,
    PRIMARY KEY (target_id, channel)
);

CREATE TABLE bookings (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id       uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    property_id      uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    room_id          uuid NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    check_in         date NOT NULL,
    check_out        date NOT NULL,
    status           text NOT NULL DEFAULT 'confirmed'
                     CHECK (status IN ('confirmed', 'pending', 'blocked', 'cancelled')),
    source           text NOT NULL DEFAULT 'manual'
                     CHECK (source IN ('manual', 'direct', 'avito', 'yandex', 'sutochno', 'ostrovok', 'other')),
    guest_name       text NOT NULL DEFAULT '',
    guest_phone      text NOT NULL DEFAULT '',
    guest_email      text NOT NULL DEFAULT '',
    guests_count     int  NOT NULL DEFAULT 1,
    total_price      numeric(12, 2) NOT NULL DEFAULT 0,
    paid_amount      numeric(12, 2) NOT NULL DEFAULT 0,
    notes            text NOT NULL DEFAULT '',
    feed_id          uuid REFERENCES ical_feeds(id) ON DELETE SET NULL,
    external_uid     text,
    hold_expires_at  timestamptz,                  -- для неоплаченных прямых броней
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (check_out > check_in),
    -- Главная защита от овербукинга: база данных физически не даст записать
    -- две активные брони одного номера с пересекающимися датами.
    CONSTRAINT bookings_no_overlap EXCLUDE USING gist (
        room_id WITH =,
        daterange(check_in, check_out, '[)') WITH &&
    ) WHERE (status <> 'cancelled')
);
CREATE INDEX bookings_account_dates_idx ON bookings (account_id, check_in, check_out);
CREATE UNIQUE INDEX bookings_feed_uid_uq ON bookings (feed_id, external_uid) WHERE feed_id IS NOT NULL;

-- Цены и ограничения по датам (перекрывают базовую цену категории)
CREATE TABLE rates (
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    room_type_id  uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    date          date NOT NULL,
    price         numeric(12, 2) CHECK (price >= 0),
    min_stay      int CHECK (min_stay > 0),
    closed        boolean NOT NULL DEFAULT false,  -- продажи закрыты
    PRIMARY KEY (room_type_id, date)
);
CREATE INDEX rates_account_idx ON rates (account_id);

-- Бронь с площадки пришла на уже занятые даты: фиксируем, чтобы владелец увидел
CREATE TABLE sync_conflicts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    feed_id       uuid REFERENCES ical_feeds(id) ON DELETE CASCADE,
    room_id       uuid REFERENCES rooms(id) ON DELETE CASCADE,
    room_type_id  uuid REFERENCES room_types(id) ON DELETE CASCADE,
    external_uid  text NOT NULL,
    check_in      date NOT NULL,
    check_out     date NOT NULL,
    summary       text NOT NULL DEFAULT '',
    detected_at   timestamptz NOT NULL DEFAULT now(),
    resolved      boolean NOT NULL DEFAULT false,
    UNIQUE (feed_id, external_uid, check_in, check_out)
);
CREATE INDEX sync_conflicts_account_idx ON sync_conflicts (account_id) WHERE NOT resolved;

CREATE TABLE sync_log (
    id           bigserial PRIMARY KEY,
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    feed_id      uuid REFERENCES ical_feeds(id) ON DELETE CASCADE,
    started_at   timestamptz NOT NULL DEFAULT now(),
    status       text NOT NULL,
    added        int NOT NULL DEFAULT 0,
    updated      int NOT NULL DEFAULT 0,
    removed      int NOT NULL DEFAULT 0,
    conflicts    int NOT NULL DEFAULT 0,
    message      text NOT NULL DEFAULT ''
);
CREATE INDEX sync_log_feed_idx ON sync_log (feed_id, started_at DESC);
