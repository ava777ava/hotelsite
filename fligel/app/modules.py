"""Модули аккаунта: необязательные разделы, которые владелец включает в «Настройки → Модули».

Базовое (всегда включено): Сегодня, Шахматка, Брони, Гости, Цены, Площадки, Уборка, Финансы, Отчёты.
Выключенный модуль: раздел скрыт в меню, фоновые задачи (автопилот, автоцены) по аккаунту не работают; данные остаются нетронутыми
и появляются снова при включении."""
from .db import one, run
from .errors import ApiError

MODULES = {
    "autopilot": {"label": "Автопилот и отзывы", "description": "Сами письма гостям, задачи и статусы уборки по расписанию, анкета гостя, код двери, сбор отзывов."},
    "autoprice": {"label": "Автоцены", "description": "Правила, которые предлагают (или сами меняют) цены в зависимости от загрузки, выходных и праздников."},
    "household": {"label": "Хозяйство", "description": "Склад расходников со списанием при уборке, счётчики воды и света, инвентарь номеров и чек-листы."},
    "analytics": {"label": "Аналитика", "description": "Прогноз загрузки и выручки, темп бронирования, отчёт по площадкам, выгрузка бухгалтеру."},
    "integrations": {"label": "Интеграции и API", "description": "Ключи доступа, вебхуки и описание API — для подключения вашего сайта или учётной системы."},
    "owners": {"label": "Собственники", "description": "Роль «Собственник», комиссия управляющей компании и отчёт собственнику."},
    "tasks": {"label": "Задачи", "description": "Список дел для сотрудников со сроками и повторами (чинить, принять бельё, проверить огнетушители)."},
}
KEYS = list(MODULES)


def enabled(conn, account_id) -> list[str]:
    row = one(conn, "SELECT modules FROM accounts WHERE id = %s", (account_id,))
    return [m for m in (row["modules"] if row else []) if m in MODULES]


def is_on(conn, account_id, key: str) -> bool:
    return key in enabled(conn, account_id)


def save(conn, account_id, keys) -> list[str]:
    if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
        raise ApiError(422, "Передайте список модулей")
    unknown = [k for k in keys if k not in MODULES]
    if unknown:
        raise ApiError(422, f"Неизвестный модуль: {unknown[0]}")
    clean = [k for k in KEYS if k in keys]   # порядок и уникальность
    run(conn, "UPDATE accounts SET modules = %s WHERE id = %s", (clean, account_id))
    return clean
