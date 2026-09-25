"""Настройки приложения из переменных окружения (.env)."""
import os
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

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/fligel")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "720"))
# Публичный адрес сервиса: из него строятся ссылки iCal для площадок
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
SYNC_INTERVAL_MINUTES = int(os.environ.get("SYNC_INTERVAL_MINUTES", "15"))
SYNC_ENABLED = os.environ.get("SYNC_ENABLED", "1") == "1"
# Сколько минут держать номер за неоплаченной прямой бронью (когда подключена оплата)
HOLD_MINUTES = int(os.environ.get("HOLD_MINUTES", "30"))
DB_POOL_MAX = int(os.environ.get("DB_POOL_MAX", "10"))
