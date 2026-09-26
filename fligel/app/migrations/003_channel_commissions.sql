-- Комиссия площадки в процентах от выручки — для отчёта «чистая выручка по источникам».
CREATE TABLE channel_commissions (
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    channel     text NOT NULL,
    percent     numeric(5, 2) NOT NULL DEFAULT 0 CHECK (percent >= 0 AND percent <= 100),
    PRIMARY KEY (account_id, channel)
);
