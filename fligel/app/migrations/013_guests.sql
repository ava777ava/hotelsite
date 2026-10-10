-- Гости: профиль (теги, заметки, день рождения, чёрный список) и шаблоны сообщений гостю.
-- Гость определяется по телефону (последние 10 цифр), отдельной таблицы «гостей» нет — брони остаются как были.

CREATE TABLE guest_profiles (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id         uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    phone_key          text NOT NULL,
    name               text NOT NULL DEFAULT '',
    tags               text[] NOT NULL DEFAULT '{}',
    notes              text NOT NULL DEFAULT '',
    birthday           date,
    blacklisted        boolean NOT NULL DEFAULT false,
    blacklist_reason   text NOT NULL DEFAULT '',
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, phone_key)
);

CREATE TABLE message_templates (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name        text NOT NULL,
    body        text NOT NULL,
    sort_order  int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX message_templates_account_idx ON message_templates (account_id);

CREATE INDEX bookings_phone_key_idx ON bookings (account_id, (right(regexp_replace(guest_phone, '\D', '', 'g'), 10)))
    WHERE guest_phone <> '';
