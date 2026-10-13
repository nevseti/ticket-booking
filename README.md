# Ticket Booking

Система бронирования билетов на культурные и спортивные мероприятия.
Курсовая работа по дисциплине «Архитектура клиент-серверных приложений».

**Стек:** FastAPI · SQLAlchemy · Alembic · PostgreSQL · Redis · RabbitMQ · React + TypeScript + Vite ·
TanStack Query · Docker Compose · nginx · GitHub Actions · k6.

## Структура

```
backend/    FastAPI-приложение (модульный монолит) и фоновый воркер
frontend/   React SPA
deploy/     nginx, docker-compose для прода, скрипты сервера
docs/       ADR, инструкции, заметки для отчёта
```

## Документация

- [Развёртывание](docs/deploy.md)
- [Архитектурные решения (ADR)](docs/adr/)
