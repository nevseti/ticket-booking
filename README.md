# Ticket Booking

Система бронирования билетов на мероприятия одной арены (хоккей, концерты, шоу): афиша,
схема зала на 8032 места в реальном времени, удержание мест, оплата с компенсацией, билеты
с QR-кодами. Курсовая работа по дисциплине «Архитектура клиент-серверных приложений».

**Работает:** https://nevseti.duckdns.org (учебный проект: мероприятия вымышленные,
оплата — имитация).

**Стек:** FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 18 · Redis 8 · RabbitMQ 4 ·
React 19 + TypeScript + Vite · TanStack Query · Mantine · SVG · SSE · OpenAPI → Orval ·
Docker Compose · nginx · GitHub Actions · k6.

**Архитектура:** модульный монолит (identity, catalog, booking, orders, notifications) +
фоновый воркер. Паттерны: MVC, Repository, Unit of Work, CQRS (модель чтения схемы зала в
Redis), Saga (оплата с компенсацией), Transactional Outbox + Inbox.

## Документация

| | |
|---|---|
| [Архитектура](docs/architecture.md) | C4 (контекст, контейнеры, компоненты), паттерны, защита от двойной продажи |
| [Последовательности](docs/sequences.md) | удержание места, сага оплаты, outbox → RabbitMQ, реальное время, перегрузка |
| [Модель данных](docs/data-model.md) | ER-диаграммы по схемам, ключи и индексы |
| [ADR](docs/adr/) | 9 архитектурных решений с обоснованием (SSE против WebSocket и др.) |
| [Нагрузочный тест](docs/loadtest-report.md) | k6: старт продаж, 10 инвариантов, Redis против PostgreSQL, найденные проблемы |
| [Развёртывание](docs/deploy.md) | VPS, TLS, CI/CD |
| [Сценарий показа](docs/demo-script.md) | что и в каком порядке показывать на защите |
| [Заметки для отчёта](docs/report-notes.md) | хронология этапов и находок |

## Структура

```
backend/    FastAPI-приложение (модульный монолит) и фоновый воркер
  app/core/       конфиг, БД (UnitOfWork), ошибки, логи, лимиты, admission control
  app/shared/     outbox, inbox
  app/modules/    identity, catalog, booking, orders, notifications
  worker/         воркер: публикатор outbox, потребители, уборщик, восстановление саг
  migrations/     Alembic
  scripts/        выгрузка OpenAPI, подготовка нагрузочного теста
frontend/   React SPA (клиент API генерируется из openapi.json)
loadtest/   сценарии k6, проверка целостности, результаты
deploy/     nginx, docker-compose для прода, скрипты сервера
docs/       документация
```

## Локальный запуск

Нужны Docker, Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 24.

```bash
docker compose up -d                      # PostgreSQL (5433), Redis, RabbitMQ, Mailpit

cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.modules.catalog.cli seed-venue    # площадка: 8032 места
uv run python -m app.modules.catalog.cli seed-demo     # 18 демо-мероприятий
uv run python -m app.modules.identity.cli create-admin --email admin@example.com
uv run uvicorn app.main:app --reload      # http://localhost:8000/api/docs
uv run python -m worker                   # воркер (в отдельном терминале)

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

Полезные команды каталога: `apply-posters` (фото демо-мероприятиям), `refresh-demo-dates`
(даты афиши от сегодня — перед показом).
