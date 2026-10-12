"""Общая механика очередей исходящих сообщений (Telegram, MAX, вебхуки): захват → отправка вне транзакции → отметка результата.

Раньше транзакция с блокировкой строк держалась на время HTTP-запросов к внешним сервисам: медленный ответ блокировал соединение
с БД, а падение процесса давало повторные отправки. Теперь:
  1. claim()  — короткая транзакция: берём пачку (FOR UPDATE SKIP LOCKED) и ставим статус 'sending';
  2. отправка идёт БЕЗ открытой транзакции;
  3. mark_sent() / mark_retry() — отдельные короткие транзакции.
Если процесс упал между 1 и 3, запись остаётся 'sending'; recover() через LEASE_MINUTES помечает её 'failed' — повторно не шлём
(лучше потерять одно уведомление, чем отправить гостю или в чат дубль)."""
import logging

from .db import all_, run, tx

log = logging.getLogger("fligel.outbox")

LEASE_MINUTES = 15
TABLES = {"telegram_outbox", "max_outbox", "webhook_deliveries"}   # имена подставляются в SQL — только из этого списка


def _check(table: str) -> str:
    if table not in TABLES:
        raise ValueError(table)
    return table


def recover(table: str) -> int:
    """Записи, зависшие в 'sending' дольше срока (процесс упал при отправке), — в 'failed', без повторной отправки."""
    table = _check(table)
    with tx() as conn:
        n = run(conn, f"UPDATE {table} SET status = 'failed', last_error = 'Процесс прервался во время отправки; повторно не отправляем, чтобы не продублировать'"
                      f" WHERE status = 'sending' AND next_attempt_at < now()")
    if n:
        log.warning("%s: %s записей зависли в отправке и помечены как неотправленные", table, n)
    return n or 0


def claim(table: str, select_sql: str, params: tuple) -> list[dict]:
    """select_sql должен выбирать строки таблицы (с id) c FOR UPDATE ... SKIP LOCKED; их статус сразу становится 'sending'."""
    table = _check(table)
    with tx() as conn:
        rows = all_(conn, select_sql, params)
        if rows:
            run(conn, f"UPDATE {table} SET status = 'sending', next_attempt_at = now() + make_interval(mins => %s) WHERE id = ANY(%s)",
                (LEASE_MINUTES, [r["id"] for r in rows]))
    return rows


def mark_sent(table: str, row_id) -> None:
    table = _check(table)
    with tx() as conn:
        run(conn, f"UPDATE {table} SET status = 'sent', sent_at = now(), last_error = NULL WHERE id = %s", (row_id,))


def mark_retry(table: str, row: dict, error: str, max_attempts: int, give_up: bool = False) -> bool:
    """Ошибка отправки: повтор с растущей паузой (2, 4, 8… минут, не больше часа) или 'failed' после max_attempts. True — окончательно."""
    table = _check(table)
    attempts = row["attempts"] + 1
    with tx() as conn:
        if give_up or attempts >= max_attempts:
            run(conn, f"UPDATE {table} SET status = 'failed', attempts = %s, last_error = %s WHERE id = %s", (attempts, error[:500], row["id"]))
            return True
        run(conn, f"UPDATE {table} SET status = 'pending', attempts = %s, last_error = %s, next_attempt_at = now() + make_interval(mins => %s) WHERE id = %s",
            (attempts, error[:500], min(2 ** attempts, 60), row["id"]))
        return False
