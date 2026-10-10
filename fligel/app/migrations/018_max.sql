-- Второй канал уведомлений — мессенджер MAX (по умолчанию выключен: нужен MAX_BOT_TOKEN в .env).
-- Устроено так же, как Telegram (005): привязка сотрудника к чату бота, очередь отправки с повторами,
-- отметка об отправленном дайджесте. Плюс у каждого сотрудника можно включать/выключать канал.

CREATE TABLE max_links (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id           uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    user_id              uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    chat_id              bigint,
    link_code            text,
    link_code_expires_at timestamptz,
    linked_at            timestamptz,
    events               text[] NOT NULL DEFAULT ARRAY['new_booking', 'cancellation', 'conflict', 'sync_error', 'digest', 'room_issue'],
    enabled              boolean NOT NULL DEFAULT true,
    created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX max_links_account_idx ON max_links (account_id);
CREATE UNIQUE INDEX max_links_code_uq ON max_links (link_code) WHERE link_code IS NOT NULL;

CREATE TABLE max_outbox (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    chat_id         bigint NOT NULL,
    text            text NOT NULL,
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    attempts        int NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    sent_at         timestamptz
);
CREATE INDEX max_outbox_due_idx ON max_outbox (next_attempt_at) WHERE status = 'pending';

CREATE TABLE max_digest_log (
    account_id     uuid PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    last_sent_date date NOT NULL
);

-- Сотрудник может отключить Telegram, не отвязывая чат
ALTER TABLE telegram_links ADD COLUMN enabled boolean NOT NULL DEFAULT true;
