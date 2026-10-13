# Ticket Booking

Система бронирования билетов на культурные и спортивные мероприятия.
Курсовая работа по дисциплине «Архитектура клиент-серверных приложений».

**Стек:** FastAPI · SQLAlchemy · Alembic · PostgreSQL · Redis · RabbitMQ · React + TypeScript + Vite ·
TanStack Query · Docker Compose · nginx · GitHub Actions · k6.

## Структура

```
backend/    FastAPI-приложение (модульный монолит) и фоновый воркер
  app/core/       конфиг, БД (UnitOfWork), ошибки, логи
  app/modules/    identity, catalog, booking, orders, notifications
  worker/         точка входа воркера (python -m worker)
  migrations/     Alembic
frontend/   React SPA
deploy/     nginx, docker-compose для прода, скрипты сервера
docs/       ADR, инструкции, заметки для отчёта
```

## Локальный запуск

Нужны Docker, Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 24.

```bash
docker compose up -d                      # PostgreSQL (5433), Redis, RabbitMQ, Mailpit

cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.modules.catalog.cli seed-venue    # площадка: 2784 места
uv run python -m app.modules.catalog.cli seed-demo     # 6 демо-мероприятий
uv run python -m app.modules.identity.cli create-admin --email admin@example.com
uv run uvicorn app.main:app --reload      # http://localhost:8000/api/docs

cd frontend
npm install
npm run dev                               # http://127.0.0.1:5173
```

Тесты и линтеры:

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run lint && npm run build
```

Сервисы для разработки: RabbitMQ UI — <http://localhost:15672> (guest/guest),
Mailpit — <http://localhost:8025>.

## Документация

- [Развёртывание на VPS](docs/deploy.md)
- [Архитектурные решения (ADR)](docs/adr/)
- [Заметки для отчёта](docs/report-notes.md)
