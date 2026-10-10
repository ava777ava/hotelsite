"""Единый слой уведомлений: одно событие → колокольчик в интерфейсе + каналы-мессенджеры (Telegram, MAX).

Код приложения вызывает только notify.send(...), а какие каналы подключены и у кого включены — решают сами
каналы (выключены по умолчанию, включаются токеном в .env). Сообщения ставятся в очередь в той же транзакции,
что и событие; реальную отправку с повторами делает фоновый планировщик (sync.run_once)."""
from . import audit, maxbot, telegram

CHANNELS = {"telegram": telegram, "max": maxbot}
CHANNEL_LABELS = {"telegram": "Telegram", "max": "MAX"}


def send(conn, account_id: str, event: str, text: str, link: str = "", bell: bool = False) -> int:
    """bell=True — ещё и запись в колокольчик (важное для людей в интерфейсе). Возвращает число поставленных
    в очередь мессенджеров сообщений."""
    if bell:
        audit.notify(conn, account_id, event, text, link)
    return sum(ch.notify(conn, account_id, event, text) for ch in CHANNELS.values())


def process_outboxes() -> dict:
    return {name: ch.process_outbox() for name, ch in CHANNELS.items()}


def send_digests() -> dict:
    return {name: ch.maybe_send_digests() for name, ch in CHANNELS.items()}
