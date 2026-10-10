-- Смена или сброс пароля завершает все ранее выданные входы (токены старше этой отметки перестают действовать).
ALTER TABLE users ADD COLUMN sessions_valid_from timestamptz NOT NULL DEFAULT 'epoch';
