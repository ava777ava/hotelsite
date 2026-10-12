"""Отправка email (сейчас только восстановление пароля).

Если SMTP не настроен (нет SMTP_HOST в .env), письма не отправляются — вместо этого
содержимое пишется в лог сервера. Этого достаточно для разработки: ссылку для
восстановления пароля можно взять из лога и открыть вручную."""
import logging
import smtplib
import threading
from email.message import EmailMessage

from . import config

log = logging.getLogger("fligel.mail")


def configured() -> bool:
    return bool(config.SMTP_HOST)


def _default_send(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
        if config.SMTP_USE_TLS:
            smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)


send = _default_send  # подменяется в тестах, как telegram.send_message и sync.fetch


def send_or_log(to: str, subject: str, body: str) -> None:
    if configured():
        send(to, subject, body)
    else:
        log.info("SMTP не настроен (режим разработки) — письмо не отправлено, вот его содержимое:\n"
                  "Кому: %s\nТема: %s\n\n%s", to, subject, body)


_pending: list[threading.Thread] = []


def send_background(to: str, subject: str, body: str) -> None:
    """Отправляет письмо в фоне, чтобы время ответа API не зависело от скорости SMTP-сервера (важно для «забыли пароль»:
    иначе по времени ответа можно понять, есть ли такой email). Сбой только пишется в лог."""
    def work():
        try:
            send_or_log(to, subject, body)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось отправить письмо на %s", to)
    t = threading.Thread(target=work, daemon=True, name="fligel-mail")
    _pending[:] = [x for x in _pending if x.is_alive()]
    _pending.append(t)
    t.start()


def flush(timeout: float = 10) -> None:
    """Дождаться фоновых писем (для тестов и аккуратной остановки)."""
    for t in list(_pending):
        t.join(timeout)
