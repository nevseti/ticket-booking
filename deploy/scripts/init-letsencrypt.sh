#!/usr/bin/env bash
# Первичный выпуск TLS-сертификата Let's Encrypt. Запускать на сервере один раз,
# когда nginx уже работает по HTTP (то есть после первого деплоя):
#   cd ~/ticket-booking && bash init-letsencrypt.sh
# Дальше сертификат продлевает контейнер certbot.
set -euo pipefail

cd ~/ticket-booking
set -a
# shellcheck disable=SC1091
source .env
set +a

: "${DOMAIN:?В .env не задан DOMAIN}"
: "${LETSENCRYPT_EMAIL:?В .env не задан LETSENCRYPT_EMAIL}"

docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d "${DOMAIN}" \
  --email "${LETSENCRYPT_EMAIL}" \
  --agree-tos --no-eff-email --non-interactive

# При старте nginx увидит сертификат и включит HTTPS-конфигурацию.
docker compose restart nginx
echo "Готово: https://${DOMAIN}"
