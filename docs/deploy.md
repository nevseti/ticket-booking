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
