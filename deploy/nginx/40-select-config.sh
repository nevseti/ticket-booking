#!/bin/sh
# Выбор конфигурации при старте контейнера:
#   - сертификата для $DOMAIN ещё нет → только HTTP (нужно, чтобы certbot прошёл проверку);
#   - сертификат есть → HTTPS + HTTP/2, HTTP перенаправляется на HTTPS.
# Запускается официальным entrypoint образа nginx перед стартом сервера.
set -eu

: "${DOMAIN:?Переменная DOMAIN обязательна}"

cert="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
if [ -f "$cert" ]; then
  template=https
else
  template=http
  echo "40-select-config: сертификата для ${DOMAIN} нет — работаем только по HTTP" >&2
fi

# Подставляем только DOMAIN: переменные nginx ($host, $uri, ...) должны остаться как есть.
# shellcheck disable=SC2016  # одинарные кавычки намеренно: это список переменных для envsubst
envsubst '${DOMAIN}' < "/etc/nginx/app/${template}.conf.template" > /etc/nginx/conf.d/default.conf

# Сертификаты продлевает контейнер certbot; периодический reload подхватывает новые файлы.
(
  while :; do
    sleep 6h
    nginx -s reload 2>/dev/null || true
  done
) &
