#!/usr/bin/env bash
# Разворачивает «Флигель» на чистом сервере Ubuntu 24.04: Docker, nginx, certbot, firewall (ufw),
# .env со сгенерированным SECRET_KEY, ежедневный бэкап по расписанию.
#
# Запуск (от root, из корня уже склонированного репозитория на сервере):
#   sudo ./deploy/setup.sh booking.вашдомен.ru you@example.ru
#
# Домен должен уже указывать A-записью на IP этого сервера — иначе certbot не выпустит
# сертификат (шаг с сертификатом можно будет повторить позже: certbot --nginx -d ваш-домен).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите от root: sudo $0 <домен> <email>" >&2
  exit 1
fi

DOMAIN="${1:-}"
EMAIL="${2:-}"
if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "Использование: sudo $0 <домен, например booking.example.ru> <email для сертификата>"
  exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
echo "==> Работаю в $REPO_DIR, домен $DOMAIN"

echo "==> Обновляю систему и ставлю пакеты (Docker, nginx, certbot, ufw)…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y docker.io docker-compose-v2 nginx certbot python3-certbot-nginx ufw curl

echo "==> Включаю и запускаю Docker…"
systemctl enable --now docker

echo "==> Настраиваю firewall (ufw): только 22 (SSH), 80 (HTTP), 443 (HTTPS)…"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Готовлю .env…"
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
  sed -i "s#^SECRET_KEY=.*#SECRET_KEY=$SECRET#" .env
  sed -i "s#^PUBLIC_BASE_URL=.*#PUBLIC_BASE_URL=https://$DOMAIN#" .env
  sed -i "s#^POSTGRES_PASSWORD=.*#POSTGRES_PASSWORD=$DB_PASS#" .env
  echo "    .env создан, SECRET_KEY и пароль базы сгенерированы автоматически."
else
  echo "    .env уже существует — не трогаю его. Проверьте вручную, что PUBLIC_BASE_URL=https://$DOMAIN"
fi

echo "==> Настраиваю nginx…"
sed "s#booking.example.ru#$DOMAIN#g" deploy/nginx.conf > /etc/nginx/sites-available/fligel
ln -sf /etc/nginx/sites-available/fligel /etc/nginx/sites-enabled/fligel
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> Собираю и запускаю приложение (docker compose)…"
docker compose up -d --build

echo "==> Жду, пока сервис ответит на /health (до 60 секунд)…"
ok=0
for _ in $(seq 1 30); do
  if curl -fs http://127.0.0.1:8000/health > /dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" -eq 1 ]; then
  echo "    Сервис отвечает."
else
  echo "    Сервис пока не отвечает — проверьте логи: docker compose logs app" >&2
fi

echo "==> Выпускаю сертификат HTTPS (certbot)…"
if certbot --nginx -d "$DOMAIN" -m "$EMAIL" --agree-tos --non-interactive --redirect; then
  echo "    Сертификат выпущен."
else
  echo "    Не удалось выпустить сертификат автоматически. Проверьте, что A-запись домена" >&2
  echo "    указывает на IP этого сервера, и повторите: certbot --nginx -d $DOMAIN" >&2
fi

echo "==> Настраиваю ежедневный бэкап (cron, 03:00, хранится последних 14)…"
chmod +x deploy/backup.sh deploy/restore.sh
CRON_LINE="0 3 * * * cd $REPO_DIR && ./deploy/backup.sh >> /var/log/fligel-backup.log 2>&1"
( crontab -l 2>/dev/null | grep -vF "deploy/backup.sh" ; echo "$CRON_LINE" ) | crontab -
touch /var/log/fligel-backup.log

cat > /etc/logrotate.d/fligel-backup <<'ROTATE'
/var/log/fligel-backup.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
}
ROTATE

echo
echo "======================================================================"
echo " Готово! Сайт:            https://$DOMAIN"
echo " Админка:                 https://$DOMAIN/app/"
echo " Проверка здоровья:       curl https://$DOMAIN/health"
echo " Логи приложения:         docker compose logs -f app"
echo " Бэкап вручную:           ./deploy/backup.sh"
echo " Бэкап по расписанию:     каждую ночь в 03:00, хранится последних 14"
echo " Восстановление:          ./deploy/restore.sh backups/имя-файла.sql.gz"
echo " Дальше: зарегистрируйте первый аккаунт на https://$DOMAIN/app/"
echo "======================================================================"
