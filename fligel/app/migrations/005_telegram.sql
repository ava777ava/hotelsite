-- Уведомления в Telegram: привязка сотрудника к чату бота, очередь исходящих сообщений
-- с повторами при сбое, отметка об уже отправленном утреннем дайджесте.
-- Всё это не используется, пока в .env не задан TELEGRAM_BOT_TOKEN (см. app/telegram.py) —
-- таблицы просто остаются пустыми.

CREATE TABLE telegram_links (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id           uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    -- один сотрудник — один чат; чтобы разные сотрудники аккаунта (владелец, администратор)
    -- получали уведомления каждый в свой Telegram, у каждого своя строка
    user_id              uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    chat_id              bigint,
    link_code            text,
    link_code_expires_at timestamptz,
    linked_at            timestamptz,
    events               text[] NOT NULL DEFAULT ARRAY['new_booking', 'cancellation', 'conflict', 'sync_error', 'digest'],
    created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX telegram_links_account_idx ON telegram_links (account_id);
-- Код привязки уникален, пока не использован (NULL после привязки/сброса — можно повторно).
CREATE UNIQUE INDEX telegram_links_code_uq ON telegram_links (link_code) WHERE link_code IS NOT NULL;

-- Исходящие сообщения. Пишутся в очередь в той же транзакции, что и событие (новая бронь,
-- отмена и т.д.) — реально отправляет их фоновый планировщик (app/sync.py), с повторами.
CREATE TABLE telegram_outbox (
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
CREATE INDEX telegram_outbox_due_idx ON telegram_outbox (next_attempt_at) WHERE status = 'pending';

-- Чтобы утренний дайджест не ушёл дважды за один день, если планировщик тикает несколько раз
-- после наступления часа отправки.
CREATE TABLE telegram_digest_log (
    account_id     uuid PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    last_sent_date date NOT NULL
);
