"""Общий журнал действий и внутренние уведомления (колокольчик)."""
from .db import run


def record(conn, account_id, user_id, action: str, summary: str, entity: str = "", entity_id=None) -> None:
    """Запись в журнал владельца: кто, что и когда сделал. Вызывать внутри той же транзакции, что и действие."""
    run(conn, "INSERT INTO audit_log (account_id, user_id, action, summary, entity, entity_id) VALUES (%s, %s, %s, %s, %s, %s)",
        (account_id, user_id, action, summary[:500], entity, entity_id))


def notify(conn, account_id, kind: str, text: str, link: str = "") -> None:
    """Внутреннее уведомление для всех сотрудников аккаунта (показывается в колокольчике)."""
    run(conn, "INSERT INTO notifications (account_id, kind, text, link) VALUES (%s, %s, %s, %s)",
        (account_id, kind, text[:500], link))
