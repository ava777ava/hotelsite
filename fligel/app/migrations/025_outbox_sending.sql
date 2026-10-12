-- Очереди сообщений: добавлен промежуточный статус 'sending'. Запись «захватывается» (pending → sending) коротким коммитом,
-- затем идёт HTTP-запрос уже вне транзакции, затем результат отмечается отдельным коммитом. Если процесс упал посреди отправки,
-- запись остаётся в 'sending' и потом помечается 'failed' — повторно мы её не шлём, чтобы не продублировать сообщение.
ALTER TABLE telegram_outbox DROP CONSTRAINT telegram_outbox_status_check;
ALTER TABLE telegram_outbox ADD CONSTRAINT telegram_outbox_status_check CHECK (status IN ('pending', 'sending', 'sent', 'failed'));
ALTER TABLE max_outbox DROP CONSTRAINT max_outbox_status_check;
ALTER TABLE max_outbox ADD CONSTRAINT max_outbox_status_check CHECK (status IN ('pending', 'sending', 'sent', 'failed'));
ALTER TABLE webhook_deliveries DROP CONSTRAINT webhook_deliveries_status_check;
ALTER TABLE webhook_deliveries ADD CONSTRAINT webhook_deliveries_status_check CHECK (status IN ('pending', 'sending', 'sent', 'failed'));
