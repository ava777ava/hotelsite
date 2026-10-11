-- События броней для вебхуков: ловим любое создание/изменение/отмену брони на уровне БД (сайт, интерфейс, API, импорт, синхронизация площадок) —
-- так ни один путь записи не пропустит событие. Отправку делает планировщик (app/webhooks.py) из очереди webhook_deliveries.

CREATE FUNCTION webhook_booking_event() RETURNS trigger AS $$
DECLARE
    ev text;
BEGIN
    IF NEW.status = 'blocked' THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'cancelled' THEN ev := 'booking.created'; END IF;
    ELSIF NEW.status = 'cancelled' AND OLD.status <> 'cancelled' THEN
        ev := 'booking.cancelled';
    ELSIF NEW.status <> 'cancelled' AND (NEW.room_id, NEW.check_in, NEW.check_out, NEW.status, NEW.guest_name, NEW.guest_phone, NEW.guest_email,
            NEW.guests_count, NEW.total_price, NEW.paid_amount, NEW.notes)
          IS DISTINCT FROM (OLD.room_id, OLD.check_in, OLD.check_out, OLD.status, OLD.guest_name, OLD.guest_phone, OLD.guest_email,
            OLD.guests_count, OLD.total_price, OLD.paid_amount, OLD.notes) THEN
        ev := 'booking.updated';
    END IF;
    IF ev IS NULL THEN
        RETURN NEW;
    END IF;
    INSERT INTO webhook_deliveries (account_id, webhook_id, event, payload)
    SELECT NEW.account_id, w.id, ev, jsonb_build_object(
        'event', ev,
        'data', jsonb_build_object(
            'id', NEW.id, 'property_id', NEW.property_id, 'room_id', NEW.room_id, 'check_in', NEW.check_in, 'check_out', NEW.check_out,
            'status', NEW.status, 'source', NEW.source, 'guest_name', NEW.guest_name, 'guest_phone', NEW.guest_phone, 'guest_email', NEW.guest_email,
            'guests_count', NEW.guests_count, 'total_price', NEW.total_price, 'paid_amount', NEW.paid_amount, 'notes', NEW.notes,
            'created_at', NEW.created_at, 'updated_at', NEW.updated_at))
    FROM webhooks w WHERE w.account_id = NEW.account_id AND w.enabled AND ev = ANY(w.events);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER bookings_webhooks AFTER INSERT OR UPDATE ON bookings FOR EACH ROW EXECUTE FUNCTION webhook_booking_event();
