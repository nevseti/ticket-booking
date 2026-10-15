#!/usr/bin/env bash
# Первичная настройка чистого VPS (Ubuntu 22.04/24.04) под проект.
# Запускать один раз от root:
#   scp deploy/scripts/bootstrap-vps.sh root@<IP>:/root/
#   ssh root@<IP> 'bash /root/bootstrap-vps.sh'
#
# Что делает:
#   1. Ставит Docker Engine + compose plugin.
#   2. Создаёт пользователя deploy (в группе docker) и переносит ему SSH-ключи root.
#   3. Включает ufw: открыты только 22, 80, 443.
#   4. Добавляет swap 2 ГБ, если RAM меньше 3 ГБ.
#   5. Создаёт каталог ~deploy/ticket-booking для docker-compose и .env.
#
# Вход по паролю НЕ отключается автоматически — сделай это вручную,
# когда убедишься, что `ssh deploy@<IP>` пускает по ключу (см. docs/deploy.md).
set -euo pipefail

APP_DIR=/home/deploy/ticket-booking
DEPLOY_USER=deploy

if [[ $EUID -ne 0 ]]; then
  echo "Запусти скрипт от root" >&2
  exit 1
fi

echo ">>> Обновление пакетов"
apt-get update -y
apt-get install -y ca-certificates curl ufw

if ! command -v docker >/dev/null 2>&1; then
  echo ">>> Установка Docker"
  curl -fsSL https://get.docker.com | sh
fi

echo ">>> Пользователь ${DEPLOY_USER}"
if ! id "${DEPLOY_USER}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "${DEPLOY_USER}"
fi
usermod -aG docker "${DEPLOY_USER}"
install -d -m 700 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "/home/${DEPLOY_USER}/.ssh"
if [[ -f /root/.ssh/authorized_keys ]]; then
  cat /root/.ssh/authorized_keys >> "/home/${DEPLOY_USER}/.ssh/authorized_keys"
  sort -u -o "/home/${DEPLOY_USER}/.ssh/authorized_keys" "/home/${DEPLOY_USER}/.ssh/authorized_keys"
  chown "${DEPLOY_USER}:${DEPLOY_USER}" "/home/${DEPLOY_USER}/.ssh/authorized_keys"
  chmod 600 "/home/${DEPLOY_USER}/.ssh/authorized_keys"
fi

echo ">>> Фаервол"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [[ ${mem_mb} -lt 3000 && ! -f /swapfile ]]; then
  echo ">>> Swap 2 ГБ (RAM: ${mem_mb} МБ)"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo ">>> Каталог приложения ${APP_DIR}"
install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${APP_DIR}"

echo
echo "Готово. Дальше:"
echo "  1. Проверь вход: ssh ${DEPLOY_USER}@<IP>"
echo "  2. Положи ${APP_DIR}/.env (шаблон — deploy/.env.prod.example)"
echo "  3. Отключи вход по паролю (docs/deploy.md, раздел «SSH»)"
