"""Настройки приложения из переменных окружения (.env)."""
import os
import time
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Часовой пояс гостиницы. Сервер и контейнеры обычно живут по UTC, и тогда «сегодня» наступало бы
# для гостей на 3 часа позже (в 01:00 по Москве система ещё считала бы вчерашний день: «Заезды
# сегодня», утренний дайджест, отметка уборки, срок заявок). Поэтому и приложение, и каждое
# подключение к базе работают в этом поясе.
APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"
os.environ["TZ"] = APP_TIMEZONE
if hasattr(time, "tzset"):  # на Windows (запуск без Docker) tzset нет — там действует часовой пояс системы
    time.tzset()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/fligel")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "720"))
# Публичный адрес сервиса: из него строятся ссылки iCal для площадок
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
SYNC_INTERVAL_MINUTES = int(os.environ.get("SYNC_INTERVAL_MINUTES", "15"))
SYNC_ENABLED = os.environ.get("SYNC_ENABLED", "1") == "1"
# Сколько минут держать номер за неоплаченной прямой бронью (когда подключена оплата)
HOLD_MINUTES = int(os.environ.get("HOLD_MINUTES", "30"))
# Через сколько часов неподтверждённая заявка с сайта сама снимается и освобождает номер (0 = не снимать).
# Без этого спам-заявки могли бы занять все номера навсегда.
REQUEST_TTL_HOURS = int(os.environ.get("REQUEST_TTL_HOURS", "48"))
# Защита публичной формы бронирования: заявок с одного IP в час и неподтверждённых заявок с одного телефона
PUBLIC_BOOKINGS_PER_HOUR = int(os.environ.get("PUBLIC_BOOKINGS_PER_HOUR", "20"))
MAX_PENDING_PER_PHONE = int(os.environ.get("MAX_PENDING_PER_PHONE", "3"))
# «Забыли пароль»: запросов в час с одного IP
RESET_REQUESTS_PER_HOUR = int(os.environ.get("RESET_REQUESTS_PER_HOUR", "10"))
DB_POOL_MAX = int(os.environ.get("DB_POOL_MAX", "10"))

# Уведомления в Telegram: полностью выключены, пока не задан токен бота (см. app/telegram.py).
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# Секрет вебхука (X-Telegram-Bot-Api-Secret-Token) — необязателен, но без него любой в интернете
# может слать запросы на /api/telegram/webhook. Задаётся при подключении вебхука в Telegram.
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
# Час (0-23) по времени сервера, после которого можно отправить утренний дайджест
TELEGRAM_DIGEST_HOUR = int(os.environ.get("TELEGRAM_DIGEST_HOUR", "8"))

# Восстановление пароля по email через SMTP. Без SMTP_HOST письма не отправляются —
# ссылка на восстановление просто пишется в лог сервера (см. app/mail.py).
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", "").strip() or SMTP_USER
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"

# Блокировка входа после подбора пароля
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
