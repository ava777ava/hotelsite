-- Общий журнал действий (кто, что, когда) и внутренние уведомления (колокольчик в интерфейсе).

CREATE TABLE audit_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,   -- NULL = система
    action      text NOT NULL,
    summary     text NOT NULL,
    entity      text NOT NULL DEFAULT '',
    entity_id   uuid,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_account_idx ON audit_log (account_id, created_at DESC);

CREATE TABLE notifications (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind        text NOT NULL,
    text        text NOT NULL,
    link        text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_account_idx ON notifications (account_id, created_at DESC);

-- Когда пользователь последний раз открывал колокольчик: всё новее — «непрочитанное»
ALTER TABLE users ADD COLUMN notifications_seen_at timestamptz NOT NULL DEFAULT now();
