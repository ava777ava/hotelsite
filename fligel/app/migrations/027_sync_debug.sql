-- Отладка синхронизации площадок: последние сырые .ics (полученные от площадки и отданные ей нами), состояние синхронизации,
-- предупреждения «площадка давно не забирала наш календарь».
ALTER TABLE accounts ADD COLUMN sync_debug boolean NOT NULL DEFAULT true;     -- режим отладки: хранить сырые календари

CREATE TABLE ical_snapshots (
    id          bigserial PRIMARY KEY,
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('received', 'served')),     -- received — забрали у площадки; served — отдали площадке
    feed_id     uuid REFERENCES ical_feeds(id) ON DELETE CASCADE,         -- для received
    target_id   uuid,                                                      -- для served: номер или категория
    channel     text NOT NULL,
    body        text NOT NULL,
    body_hash   text NOT NULL,
    size        int NOT NULL,
    events      int NOT NULL DEFAULT 0,
    status      text NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error')),
    note        text NOT NULL DEFAULT '',
    user_agent  text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),                       -- такой же календарь пришёл/ушёл ещё раз (копия не плодится)
    seen_count  int NOT NULL DEFAULT 1
);
CREATE INDEX ical_snapshots_feed_idx ON ical_snapshots (feed_id, created_at DESC) WHERE kind = 'received';
CREATE INDEX ical_snapshots_target_idx ON ical_snapshots (target_id, channel, created_at DESC) WHERE kind = 'served';
CREATE INDEX ical_snapshots_account_idx ON ical_snapshots (account_id, created_at DESC);

ALTER TABLE ical_exports ADD COLUMN last_user_agent text NOT NULL DEFAULT '';

ALTER TABLE sync_log ADD COLUMN events int NOT NULL DEFAULT 0;     -- сколько событий было в календаре площадки
ALTER TABLE sync_log ADD COLUMN echoes int NOT NULL DEFAULT 0;     -- сколько из них отброшено как «эхо» наших броней
ALTER TABLE sync_log ADD COLUMN skipped int NOT NULL DEFAULT 0;    -- сколько событий не удалось разобрать

-- Предупреждения по площадкам: открытая запись = площадка не забирала наш календарь дольше порога (по одному разу уведомляем)
CREATE TABLE sync_alerts (
    account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    target_id   uuid NOT NULL,
    channel     text NOT NULL,
    kind        text NOT NULL DEFAULT 'export_stale',
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (target_id, channel, kind)
);
CREATE INDEX sync_alerts_account_idx ON sync_alerts (account_id);
