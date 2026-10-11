#!/usr/bin/env bash
# Проверка, что бэкап реально восстанавливается: берёт последний файл из backups/, разворачивает его во ВРЕМЕННУЮ базу,
# проверяет её (данные на месте, защита от двойных броней bookings_no_overlap на месте, миграции не «из будущего»),
# удаляет временную базу и записывает результат в рабочую базу — он виден в /health (поле backup_check).
#
# Запуск вручную:       ./deploy/verify_backup.sh [файл-бэкапа.sql.gz]
# По расписанию (cron): раз в неделю — ставится скриптом deploy/setup.sh (воскресенье, 04:00).
# Рабочую базу НЕ трогает (кроме одной записи с результатом). Код возврата 0 — бэкап в порядке, 1 — нет.
set -uo pipefail
cd "$(dirname "$0")/.."
_URL_FROM_ENV="${DATABASE_URL:-}"
[ -f .env ] && set -a && source .env && set +a
[ -n "$_URL_FROM_ENV" ] && DATABASE_URL="$_URL_FROM_ENV"   # явно заданный в окружении адрес важнее .env

BACKUP_DIR="${FLIGEL_BACKUP_DIR:-$(pwd)/backups}"
FILE="${1:-$(ls -1t "$BACKUP_DIR"/fligel_*.sql.gz 2>/dev/null | head -n 1)}"
TMPDB="fligel_verify_$(date +%s)"
DB="${POSTGRES_DB:-fligel}"
PGU="${POSTGRES_USER:-fligel}"

if docker compose ps db 2>/dev/null | grep -qi "running\|Up"; then
  PSQL_ADMIN=(docker compose exec -T db psql -U "$PGU" -d postgres -v ON_ERROR_STOP=1 -qtAX)
  PSQL_TMP=(docker compose exec -T db psql -U "$PGU" -d "$TMPDB" -v ON_ERROR_STOP=1 -qtAX)
  PSQL_PROD=(docker compose exec -T db psql -U "$PGU" -d "$DB" -v ON_ERROR_STOP=1 -qtAX)
else
  : "${DATABASE_URL:?Не найден DATABASE_URL. Задайте его в .env}"
  BASE_URL="${DATABASE_URL%%\?*}"
  PSQL_ADMIN=(psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -qtAX)
  PSQL_TMP=(psql "${BASE_URL%/*}/$TMPDB" -v ON_ERROR_STOP=1 -qtAX)
  PSQL_PROD=("${PSQL_ADMIN[@]}")
fi

RESULT_OK=false
MESSAGE=""
ACCOUNTS=0
BOOKINGS=0
cleanup() { "${PSQL_ADMIN[@]}" -c "DROP DATABASE IF EXISTS \"$TMPDB\" WITH (FORCE)" >/dev/null 2>&1 || true; }
trap cleanup EXIT

record() {  # записываем результат в рабочую базу (виден в /health)
  local json
  json=$(printf '{"ok": %s, "at": "%s", "file": "%s", "accounts": %s, "bookings": %s, "message": "%s"}' \
    "$RESULT_OK" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(basename "${FILE:-нет}")" "$ACCOUNTS" "$BOOKINGS" "$MESSAGE")
  "${PSQL_PROD[@]}" -c "INSERT INTO service_state (key, value) VALUES ('backup_check', \$j\$${json}\$j\$) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()" >/dev/null 2>&1 \
    || echo "Не удалось записать результат проверки в базу (проверьте доступ)"
  echo "$json"
}
fail() { MESSAGE="$1"; echo "ПРОВЕРКА БЭКАПА НЕ ПРОЙДЕНА: $1"; record; exit 1; }

[ -n "${FILE:-}" ] && [ -f "$FILE" ] || fail "нет файла бэкапа в $BACKUP_DIR"
[ -s "$FILE" ] || fail "файл бэкапа пустой"
gzip -t "$FILE" 2>/dev/null || fail "файл бэкапа повреждён (не читается как gzip)"

echo "Проверяю $FILE → временная база $TMPDB"
"${PSQL_ADMIN[@]}" -c "CREATE DATABASE \"$TMPDB\"" >/dev/null || fail "не удалось создать временную базу (нужны права CREATEDB)"
gunzip -c "$FILE" | "${PSQL_TMP[@]}" >/dev/null 2>/tmp/fligel_verify_err.txt || fail "восстановление завершилось ошибкой: $(head -c 200 /tmp/fligel_verify_err.txt | tr '\n"' '  ')"

ACCOUNTS=$("${PSQL_TMP[@]}" -c "SELECT count(*) FROM accounts") || fail "в восстановленной базе нет таблицы accounts"
BOOKINGS=$("${PSQL_TMP[@]}" -c "SELECT count(*) FROM bookings") || fail "в восстановленной базе нет таблицы bookings"
[ "$ACCOUNTS" -ge 1 ] || fail "в восстановленной базе нет ни одного аккаунта"
GUARD=$("${PSQL_TMP[@]}" -c "SELECT count(*) FROM pg_constraint WHERE conname = 'bookings_no_overlap'")
[ "$GUARD" = "1" ] || fail "в восстановленной базе нет защиты от двойных броней (bookings_no_overlap)"
LAST_BACKUP_MIG=$("${PSQL_TMP[@]}" -c "SELECT max(name) FROM schema_migrations")
LAST_PROD_MIG=$("${PSQL_PROD[@]}" -c "SELECT max(name) FROM schema_migrations")
if [[ "$LAST_BACKUP_MIG" > "$LAST_PROD_MIG" ]]; then fail "бэкап новее рабочей базы по миграциям ($LAST_BACKUP_MIG > $LAST_PROD_MIG)"; fi

RESULT_OK=true
MESSAGE="восстановлен: аккаунтов $ACCOUNTS, броней $BOOKINGS, последняя миграция $LAST_BACKUP_MIG"
echo "OK: $MESSAGE"
record
