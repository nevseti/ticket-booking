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

# Email необязателен: на него Let's Encrypt шлёт предупреждения, если продление сломалось.
if [[ -n "${LETSENCRYPT_EMAIL:-}" ]]; then
  email_args=(--email "${LETSENCRYPT_EMAIL}" --no-eff-email)
else
  email_args=(--register-unsafely-without-email)
fi

docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d "${DOMAIN}" \
  "${email_args[@]}" \
  --agree-tos --non-interactive

# При старте nginx увидит сертификат и включит HTTPS-конфигурацию.
docker compose restart nginx
echo "Готово: https://${DOMAIN}"
