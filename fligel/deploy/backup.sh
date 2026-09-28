#!/usr/bin/env bash
# Ежедневный бэкап базы данных: pg_dump в сжатый файл, хранится последних 14 штук.
#
# Запуск вручную:      ./deploy/backup.sh
# По расписанию (cron): ставится автоматически скриптом deploy/setup.sh
#   (crontab: 0 3 * * * /opt/fligel/deploy/backup.sh >> /var/log/fligel-backup.log 2>&1)
#
# Работает как с docker compose (по умолчанию для этого проекта), так и с обычной
# установкой PostgreSQL — во втором случае просто использует DATABASE_URL из .env.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && source .env && set +a

BACKUP_DIR="${FLIGEL_BACKUP_DIR:-$(pwd)/backups}"
KEEP="${FLIGEL_BACKUP_KEEP:-14}"
mkdir -p "$BACKUP_DIR"

STAMP=$(date +%Y-%m-%d_%H-%M-%S)
FILE="$BACKUP_DIR/fligel_$STAMP.sql.gz"
TMP="$FILE.tmp"

cleanup() { rm -f "$TMP"; }
trap cleanup EXIT

if docker compose ps db 2>/dev/null | grep -qi "running\|Up"; then
  echo "Бэкап через docker compose (сервис db)…"
  docker compose exec -T db pg_dump -U "${POSTGRES_USER:-fligel}" "${POSTGRES_DB:-fligel}" | gzip > "$TMP"
else
  echo "docker compose не запущен — бэкап напрямую через DATABASE_URL…"
  : "${DATABASE_URL:?Не найден DATABASE_URL. Задайте его в .env или запустите docker compose up -d}"
  pg_dump "$DATABASE_URL" | gzip > "$TMP"
fi

mv "$TMP" "$FILE"
trap - EXIT
echo "Бэкап сохранён: $FILE ($(du -h "$FILE" | cut -f1))"

COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -name 'fligel_*.sql.gz' | wc -l)
if [ "$COUNT" -gt "$KEEP" ]; then
  # shellcheck disable=SC2012
  ls -1t "$BACKUP_DIR"/fligel_*.sql.gz | tail -n "+$((KEEP + 1))" | xargs -r rm -f
  echo "Старые бэкапы удалены, оставлено последних: $KEEP"
fi
