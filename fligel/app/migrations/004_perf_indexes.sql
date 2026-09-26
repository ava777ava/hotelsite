-- Индексы для быстрой работы шахматки, отчётов и списка расходов на больших объёмах данных.
-- Board и отчёты фильтруют брони/расходы по property_id (а не только по account_id), поэтому
-- отдельный индекс по account_id тут не помогает — нужен по property_id.
CREATE INDEX bookings_property_dates_idx ON bookings (property_id, check_in, check_out);
CREATE INDEX expenses_property_date_idx ON expenses (property_id, date) WHERE property_id IS NOT NULL;
