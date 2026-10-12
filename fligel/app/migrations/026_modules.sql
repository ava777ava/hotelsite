-- Модули аккаунта («Настройки → Модули»): необязательные разделы включаются владельцем. Базовое (Сегодня, Шахматка, Брони, Гости,
-- Цены, Площадки, Уборка, Финансы, Отчёты) включено всегда и здесь не хранится.
ALTER TABLE accounts ADD COLUMN modules text[] NOT NULL DEFAULT '{}';

-- Существующим аккаунтам оставляем включённым то, чем они уже пользуются (есть данные).
UPDATE accounts a SET modules = ARRAY(
    SELECT m FROM (VALUES
        ('autopilot',    EXISTS (SELECT 1 FROM automation_runs x WHERE x.account_id = a.id)
                         OR EXISTS (SELECT 1 FROM reviews x WHERE x.account_id = a.id)
                         OR EXISTS (SELECT 1 FROM booking_forms x WHERE x.account_id = a.id)
                         OR EXISTS (SELECT 1 FROM automation_rules x WHERE x.account_id = a.id AND x.preset IS NULL)),
        ('autoprice',    EXISTS (SELECT 1 FROM price_rules x WHERE x.account_id = a.id)
                         OR EXISTS (SELECT 1 FROM price_settings x WHERE x.account_id = a.id AND x.mode <> 'off')
                         OR EXISTS (SELECT 1 FROM price_changes x WHERE x.account_id = a.id)),
        ('household',    EXISTS (SELECT 1 FROM stock_items x WHERE x.account_id = a.id)
                         OR EXISTS (SELECT 1 FROM meters x WHERE x.account_id = a.id)
                         OR EXISTS (SELECT 1 FROM inventory_items x WHERE x.account_id = a.id)),
        ('analytics',    EXISTS (SELECT 1 FROM bookings x WHERE x.account_id = a.id)),
        ('integrations', EXISTS (SELECT 1 FROM api_keys x WHERE x.account_id = a.id)
                         OR EXISTS (SELECT 1 FROM webhooks x WHERE x.account_id = a.id)),
        ('owners',       EXISTS (SELECT 1 FROM users x WHERE x.account_id = a.id AND x.role = 'landlord')
                         OR EXISTS (SELECT 1 FROM properties x WHERE x.account_id = a.id AND x.mc_commission_percent > 0)),
        ('tasks',        EXISTS (SELECT 1 FROM tasks x WHERE x.account_id = a.id))
    ) AS t(m, used) WHERE used
);
