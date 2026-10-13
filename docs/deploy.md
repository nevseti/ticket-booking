# Развёртывание на VPS

## 1. Домен (DuckDNS)

Без домена не получится выпустить TLS-сертификат, а без HTTPS не работают HTTP/2
(нужен для SSE) и cookie с флагом `Secure`.

1. Зайди на <https://www.duckdns.org> через GitHub.
2. Создай поддомен, например `tickets-<фамилия>` → получится `tickets-<фамилия>.duckdns.org`.
3. В поле `current ip` впиши IP своего VPS и нажми `update ip`.
4. Проверь: `nslookup tickets-<фамилия>.duckdns.org` должен вернуть IP сервера.

Позже можно перейти на свой домен (`.ru` ~200–300 ₽/год): поменять `DOMAIN` в `.env`
на сервере и перевыпустить сертификат (раздел 4).

## 2. Первичная настройка сервера

```bash
scp deploy/scripts/bootstrap-vps.sh root@<IP>:/root/
ssh root@<IP> 'bash /root/bootstrap-vps.sh'
ssh deploy@<IP>   # должен пустить по ключу
```

### SSH: отключить вход по паролю

Только после того, как вход `deploy@<IP>` по ключу заработал:

```bash
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
```

### Ключ для GitHub Actions

Деплой из CI ходит на сервер отдельным ключом, не личным:

```bash
ssh-keygen -t ed25519 -f ./gh-deploy -N "" -C "github-actions-deploy"
ssh-copy-id -i ./gh-deploy.pub deploy@<IP>
```

Приватную часть (`gh-deploy`) положи в секрет репозитория `DEPLOY_SSH_KEY`, файл удали.

## 3. Настройка GitHub

1. Создай репозиторий и запушь код (`git remote add origin …`, `git push -u origin main --all`).
2. **Settings → Secrets and variables → Actions:**
   - секрет `DEPLOY_SSH_KEY` — приватный ключ `gh-deploy` из раздела 2;
   - переменная `DEPLOY_HOST` — домен или IP сервера (например, `tickets-<фамилия>.duckdns.org`);
   - переменная `DEPLOY_USER` — `deploy` (можно не задавать, это значение по умолчанию).
3. **Settings → Environments** — создай окружение `production` (по желанию — с ручным
   подтверждением деплоя).

Пока `DEPLOY_HOST` не задан, workflow `Deploy` только собирает и публикует образы в GHCR,
а шаг выкладки пропускает.

## 4. Первый деплой

На сервере положи `/opt/ticket-booking/.env` по шаблону `deploy/.env.prod.example`
(секреты — `openssl rand -hex 32`). Затем пуш в `main` → CI → Deploy:

- образы `ticket-booking-api` и `ticket-booking-web` публикуются в GHCR с тегом-хэшем коммита;
- на сервер копируются `docker-compose.yml` и скрипты;
- `remote-deploy.sh` обновляет теги в `.env`, скачивает образы и перезапускает сервисы;
- сервис `migrate` применяет миграции до старта `api` и `worker`.

Пока сертификата нет, nginx работает по HTTP: `http://<домен>/api/health`.

## 5. TLS-сертификат

Один раз, после первого деплоя:

```bash
ssh deploy@<домен>
cd /opt/ticket-booking && bash init-letsencrypt.sh
```

Скрипт выпускает сертификат Let's Encrypt (проверка HTTP-01 через nginx) и перезапускает
nginx — при старте он находит сертификат и включает HTTPS + HTTP/2. Продление — контейнер
`certbot` (раз в 12 ч), nginx перечитывает сертификаты каждые 6 ч.

## Полезные команды на сервере

```bash
cd /opt/ticket-booking
docker compose exec api python -m app.modules.identity.cli create-admin --email <email>
docker compose exec api python -m app.modules.catalog.cli seed-demo   # демо-мероприятия
docker compose ps                     # состояние сервисов
docker compose logs -f api worker     # логи
docker compose exec postgres psql -U tickets tickets
ssh -L 15672:localhost:15672 deploy@<домен>   # RabbitMQ UI на http://localhost:15672
```
