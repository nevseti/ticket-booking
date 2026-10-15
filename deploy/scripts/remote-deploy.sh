#!/usr/bin/env bash
# Выполняется на сервере из GitHub Actions:
#   remote-deploy.sh <api_image> <web_image> <tag>
# Записывает образы в .env, скачивает их и перезапускает изменившиеся сервисы.
# Миграции выполняются сервисом migrate, от которого зависят api и worker.
set -euo pipefail

APP_DIR="${HOME}/ticket-booking"
API_IMAGE=$1
WEB_IMAGE=$2
TAG=$3

cd "${APP_DIR}"
test -f .env || { echo "Нет ${APP_DIR}/.env — см. deploy/.env.prod.example" >&2; exit 1; }

set_env() {
  local key=$1 value=$2
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

set_env API_IMAGE "${API_IMAGE}"
set_env WEB_IMAGE "${WEB_IMAGE}"
set_env IMAGE_TAG "${TAG}"

docker compose pull --quiet nginx api worker migrate
docker compose up -d --remove-orphans

# Ждём, пока api пройдёт healthcheck (миграции выполняются до его старта).
for _ in $(seq 1 60); do
  status=$(docker compose ps api --format '{{.Health}}')
  [[ "${status}" == "healthy" ]] && break
  sleep 2
done
if [[ "${status}" != "healthy" ]]; then
  echo "api не стал healthy (статус: ${status})" >&2
  docker compose logs --tail 50 migrate api >&2
  exit 1
fi

docker image prune -f >/dev/null

echo "Развёрнута версия ${TAG}"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
