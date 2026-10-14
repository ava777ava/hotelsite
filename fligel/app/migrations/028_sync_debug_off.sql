-- Режим отладки площадок по умолчанию выключен: в сырых календарях бывают имена гостей и другие персональные данные,
-- копить их без явного решения владельца не нужно (минимизация данных, 152-ФЗ). Включается в «Площадки → Состояние синхронизации».
ALTER TABLE accounts ALTER COLUMN sync_debug SET DEFAULT false;
UPDATE accounts SET sync_debug = false;
DELETE FROM ical_snapshots;
