# Модель данных

PostgreSQL 18, у каждого модуля своя схема. Внешние ключи — **только внутри модуля**: связи
между модулями логические (по id) и через события. Так модули можно было бы разнести по
разным БД без переписывания (ADR 0001). Миграции — Alembic, `backend/migrations/`.

## Схема зала и мероприятия (catalog)

```mermaid
erDiagram
    venues ||--o{ sections : "секторы"
    sections ||--o{ seats : "места"
    price_categories ||--o{ seats : "категория места"
    events ||--o{ event_prices : "цены"
    price_categories ||--o{ event_prices : ""

    venues {
        smallint id PK
        varchar name
        int width "viewBox схемы"
        int height
        text stage_path "контур сцены (SVG)"
        float rink_x "ледовая площадка"
        smallint layout_version "версия схемы зала"
        jsonb boxes "корпоративные ложи (не продаются)"
    }
    sections {
        smallint id PK
        smallint venue_id FK
        varchar code UK "101, V03, L05, FAN…"
        varchar name
        text path "контур (SVG)"
        varchar kind "seated | standing"
        varchar_array configs "hockey, stage"
    }
    seats {
        int id PK
        smallint section_id FK
        varchar row
        smallint number "UQ (section_id, row, number)"
        float x
        float y
        smallint price_category_id FK
    }
    price_categories {
        smallint id PK "1 VIP … 7 Лаунж"
        varchar name
        varchar color
    }
    events {
        uuid id PK "uuidv7()"
        varchar title
        varchar kind "concert | show | sport → режим зала"
        varchar status "draft | published | cancelled"
        timestamptz starts_at
        timestamptz sales_start_at
        timestamptz sales_end_at
        varchar poster_url
    }
    event_prices {
        uuid event_id PK,FK
        smallint price_category_id PK,FK
        int price_kopecks "CHECK > 0"
    }
```

Схема зала — справочные данные: генерируется кодом (`catalog/venue_layout.py`), засевается
`seed-venue` и кэшируется в памяти процесса. Стоячая зона хранится как набор безымянных мест
(`row = ''`): билет в зону занимает одно из них.

## Бронирование (booking)

```mermaid
erDiagram
    holds {
        uuid id PK
        uuid event_id "→ catalog.events"
        int seat_id "→ catalog.seats"
        uuid user_id "→ identity.users"
        varchar status "active | released | expired | converted"
        timestamptz expires_at "через 10 мин, на оплату продлевается"
        timestamptz closed_at
    }
    sold_seats {
        uuid event_id PK
        int seat_id PK "второй рубеж от двойной продажи"
        uuid order_id "→ orders.orders"
        timestamptz sold_at
    }
```

| Индекс / ключ | Назначение |
|---|---|
| `ux_holds_active_seat (event_id, seat_id) WHERE status = 'active'` UNIQUE | **Главная защита:** одно активное удержание на место |
| `ix_holds_active_user (user_id, event_id) WHERE active` | Лимит 6 мест на пользователя |
| `ix_holds_active_expires (expires_at) WHERE active` | Уборщик просроченных удержаний |
| PK `sold_seats (event_id, seat_id)` | Место продаётся один раз |

Истечение ленивое: `now()` нельзя использовать в предикате индекса, поэтому просроченное
удержание остаётся «active», пока его не погасят. Это делает захват этого же места или
уборщик в воркере раз в 15 с (`FOR UPDATE SKIP LOCKED`).

## Заказы и оплата (orders)

```mermaid
erDiagram
    checkouts ||--o| orders : "успешная сага"
    orders ||--|{ tickets : "билеты"

    checkouts {
        uuid id PK "он же ключ идемпотентности у банка"
        uuid user_id
        uuid event_id
        varchar idempotency_key "UQ (user_id, idempotency_key)"
        varchar state "started | paid | completed | failed"
        int amount_kopecks
        uuid_array hold_ids
        jsonb items "что покупается (снимок цен)"
        varchar payment_ref
        varchar failure_reason
        uuid order_id
    }
    orders {
        uuid id PK
        uuid user_id
        uuid event_id
        uuid checkout_id UK
        int total_kopecks
        varchar payment_ref
    }
    tickets {
        uuid id PK
        uuid order_id FK
        uuid event_id
        int seat_id "UQ (event_id, seat_id) — третий рубеж"
        varchar section_name "копия: билет читается без справочника"
        varchar row
        int number
        int price_kopecks
        varchar code UK "TB1.<id>.<HMAC> — в QR"
    }
    mock_payments {
        uuid id PK
        varchar idempotency_key UK "= checkout.id"
        int amount_kopecks
        varchar status "succeeded | declined | refunded"
        timestamptz refunded_at
    }
```

Билет хранит сектор, ряд, номер и цену текстом, поэтому он остаётся читаемым и после
перестройки схемы зала.

## Пользователи, уведомления, инфраструктура

```mermaid
erDiagram
    users {
        uuid id PK
        varchar email UK "в нижнем регистре"
        varchar name
        varchar password_hash "Argon2id"
        varchar role "user | admin"
    }
    notifications {
        uuid id PK
        uuid user_id "→ identity.users"
        varchar kind "order_paid | checkout_failed"
        varchar title
        text body
        varchar link
        timestamptz read_at
    }
    outbox {
        bigint id PK "порядок публикации"
        uuid event_id UK "message_id в RabbitMQ"
        varchar event_type "booking.seats_held, orders.order_paid…"
        varchar aggregate_id
        jsonb payload
        timestamptz published_at "NULL — ещё не опубликовано"
    }
    processed_messages {
        varchar consumer PK
        uuid message_id PK "inbox: повтор не обрабатывается"
        timestamptz processed_at
    }
```

`identity.users`, `notifications.notifications`, `infra.outbox` и
`infra.processed_messages` лежат в разных схемах. Outbox и inbox — общая инфраструктура
(`app/shared`), ими пользуются все модули.

## Модель чтения в Redis (не таблица, а проекция)

| Ключ | Содержимое |
|---|---|
| `seatmap:v{версия схемы}:{event_id}` (HASH) | `v` — версия; `s{место}` — h/s у сидячих мест; `p{место}` — у мест стоячих зон; `z{зона}` — занято в зоне |
| канал `seatmap-live:{event_id}` | изменения `{v, seats, zones}` для SSE |
| `rl:{правило}:{субъект}` (HASH) | ведро token bucket: жетоны и время |

Всё в Redis можно пересобрать из PostgreSQL. Поэтому Redis работает с
`maxmemory-policy allkeys-lru` и при нехватке памяти вытесняет ключи, а не отказывает в
записи.
