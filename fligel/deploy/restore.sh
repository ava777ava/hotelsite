#!/usr/bin/env bash
# Восстановление базы данных из бэкапа, сделанного deploy/backup.sh.
#
#   ./deploy/restore.sh backups/fligel_2026-01-01_03-00-00.sql.gz
#
# ВНИМАНИЕ: полностью удаляет текущую базу и заменяет её содержимым из файла.
# Приложение на время восстановления останавливается (иначе оно продолжит писать в базу,
# пока мы её пересоздаём, и часть данных потеряется).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && source .env && set +a

FILE="${1:-}"
if [ -z "$FILE" ]; then
  echo "Использование: $0 <файл-бэкапа.sql.gz>"
  echo "Доступные бэкапы:"
  ls -1t "${FLIGEL_BACKUP_DIR:-$(pwd)/backups}"/fligel_*.sql.gz 2>/dev/null || echo "  (не найдено)"
  exit 1
fi
[ -f "$FILE" ] || { echo "Файл не найден: $FILE"; exit 1; }

echo "Это ПОЛНОСТЬЮ заменит текущую базу данными из: $FILE"
read -r -p "Продолжить? Наберите «да»: " ans
[ "$ans" = "да" ] || { echo "Отменено."; exit 1; }

DB="${POSTGRES_DB:-fligel}"
USER="${POSTGRES_USER:-fligel}"

if docker compose ps db 2>/dev/null | grep -qi "running\|Up"; then
  echo "Останавливаю приложение…"
  docker compose stop app
  echo "Пересоздаю базу…"
  docker compose exec -T db psql -U "$USER" -d postgres -c "DROP DATABASE IF EXISTS $DB WITH (FORCE)"
  docker compose exec -T db psql -U "$USER" -d postgres -c "CREATE DATABASE $DB"
  echo "Восстанавливаю данные…"
  gunzip -c "$FILE" | docker compose exec -T db psql -U "$USER" -d "$DB"
  echo "Запускаю приложение…"
  docker compose start app
else
  : "${DATABASE_URL:?Не найден DATABASE_URL. Задайте его в .env}"
  echo "Восстанавливаю напрямую через DATABASE_URL…"
  gunzip -c "$FILE" | psql "$DATABASE_URL"
fi
echo "Готово. Проверьте /health и вход в приложение."
