-- Роль «Собственник» (только чтение своих объектов) и комиссия управляющей компании.

ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('owner', 'manager', 'housekeeper', 'landlord'));

CREATE TABLE user_properties (
    account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, property_id)
);
CREATE INDEX user_properties_property_idx ON user_properties (property_id);

ALTER TABLE properties
    ADD COLUMN mc_commission_percent numeric(5, 2) NOT NULL DEFAULT 0 CHECK (mc_commission_percent BETWEEN 0 AND 100),
    ADD COLUMN mc_commission_base    text NOT NULL DEFAULT 'net' CHECK (mc_commission_base IN ('gross', 'net'));
