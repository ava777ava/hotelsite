-- Настройки сотрудника и служебные отметки.
ALTER TABLE users ADD COLUMN notify_email boolean NOT NULL DEFAULT true;   -- письма о новых заявках с сайта
ALTER TABLE users ADD COLUMN last_login_at timestamptz;                    -- последний вход (для поддержки клиентов)
