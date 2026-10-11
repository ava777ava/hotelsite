-- Продажа сервиса: операторская панель, счета без платёжного провайдера, напоминания об оплате, публичный API (ключи, вебхуки), демо-аккаунт.

CREATE TABLE operators (                       -- сотрудники сервиса (не клиенты): свой вход, свои права
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          text NOT NULL,
    name           text NOT NULL DEFAULT '',
    password_hash  text NOT NULL,
    failed_attempts int NOT NULL DEFAULT 0,
    locked_until   timestamptz,
    last_login_at  timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX operators_email_uq ON operators (lower(email));

ALTER TABLE accounts
    ADD COLUMN operator_notes text NOT NULL DEFAULT '',          -- заметки оператора о клиенте
    ADD COLUMN is_demo boolean NOT NULL DEFAULT false;           -- публичная песочница: ограничения и ежедневный сброс

CREATE SEQUENCE invoice_seq;
CREATE TABLE invoices (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    number       text NOT NULL UNIQUE,                            -- ГГГГ-NNNN
    plan         text NOT NULL,
    months       int NOT NULL DEFAULT 1 CHECK (months BETWEEN 1 AND 36),
    amount       numeric(12, 2) NOT NULL CHECK (amount >= 0),
    status       text NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'paid', 'cancelled')),
    issued_on    date NOT NULL DEFAULT current_date,
    paid_on      date,
    period_from  date,                                            -- какой период оплачен (заполняется при отметке «оплачен»)
    period_to    date,
    note         text NOT NULL DEFAULT '',
    created_by   uuid REFERENCES operators(id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX invoices_account_idx ON invoices (account_id, issued_on DESC);

CREATE TABLE billing_notices (                  -- какие напоминания клиенту уже отправлены (чтобы не повторять)
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    key         text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, key)
);

CREATE TABLE service_state (                    -- мелкие служебные отметки планировщика (например, когда сбрасывали демо)
    key    text PRIMARY KEY,
    value  text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- публичный API ----------
CREATE TABLE api_keys (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name          text NOT NULL,
    prefix        text NOT NULL,                                  -- первые символы ключа — показываем в списке
    key_hash      text NOT NULL UNIQUE,                           -- хранится только хэш; сам ключ виден один раз при создании
    scope         text NOT NULL DEFAULT 'read' CHECK (scope IN ('read', 'write')),
    created_by    uuid REFERENCES users(id) ON DELETE SET NULL,
    last_used_at  timestamptz,
    revoked_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX api_keys_account_idx ON api_keys (account_id);

CREATE TABLE webhooks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    url           text NOT NULL,
    secret        text NOT NULL,                                  -- подпись HMAC-SHA256 каждого запроса
    events        text[] NOT NULL DEFAULT ARRAY['booking.created', 'booking.updated', 'booking.cancelled'],
    enabled       boolean NOT NULL DEFAULT true,
    last_status   text NOT NULL DEFAULT '',
    last_delivery_at timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX webhooks_account_idx ON webhooks (account_id);

CREATE TABLE webhook_deliveries (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id       uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    webhook_id       uuid NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event            text NOT NULL,
    payload          jsonb NOT NULL,
    status           text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    attempts         int NOT NULL DEFAULT 0,
    next_attempt_at  timestamptz NOT NULL DEFAULT now(),
    last_error       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    sent_at          timestamptz
);
CREATE INDEX webhook_deliveries_due_idx ON webhook_deliveries (next_attempt_at) WHERE status = 'pending';
CREATE INDEX webhook_deliveries_hook_idx ON webhook_deliveries (webhook_id, created_at DESC);
