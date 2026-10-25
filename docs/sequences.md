# Диаграммы последовательностей

Ключевые сценарии системы. Архитектура в целом — [architecture.md](architecture.md).

## 1. Удержание места

Клик по месту на схеме. Защита от двойной продажи — в одном операторе INSERT.

```mermaid
sequenceDiagram
    autonumber
    actor U as Покупатель
    participant B as Браузер (SPA)
    participant N as nginx
    participant A as API (booking)
    participant C as catalog (фасад)
    participant P as PostgreSQL

    U->>B: клик по свободному месту
    B->>B: место сразу показано «вашим» (оптимистично)
    B->>N: POST /api/events/{id}/holds {seat_id}
    N->>N: limit_req (по IP)
    N->>A: проксирование
    A->>A: admission (мест в очереди?) → лимит на пользователя (Redis) → JWT
    A->>C: get_event, get_seats (справочник в памяти)
    C-->>A: продажи открыты? место продаётся в этом режиме зала, есть цена?
    A->>P: BEGIN, advisory lock (пользователь, мероприятие)
    A->>P: лимит 6 мест на пользователя, погасить просроченное удержание места
    A->>P: INSERT hold … WHERE NOT EXISTS(sold) ON CONFLICT (активное) DO NOTHING RETURNING
    alt место свободно
        P-->>A: удержание
        A->>P: перепроверка продажи (новый снимок)
        A->>P: INSERT outbox booking.seats_held
        A->>P: COMMIT
        A-->>B: 201 {hold, expires_at через 10 мин}
    else место уже занято
        P-->>A: пусто
        A->>P: ROLLBACK
        A-->>B: 409 SEAT_UNAVAILABLE
        B->>U: «Это место только что заняли»
    end
```

## 2. Оплата: сага с компенсацией

Оплата — внешний вызов, поэтому каждый шаг саги — своя короткая транзакция, а банк
вызывается вне транзакции.

```mermaid
sequenceDiagram
    autonumber
    actor U as Покупатель
    participant A as API (orders: сага)
    participant P as PostgreSQL
    participant K as Банк (имитатор)
    participant W as Воркер

    U->>A: POST /api/checkout {event_id, card} + Idempotency-Key
    A->>P: tx1: есть сага с этим ключом? → вернуть её (повтор не платит дважды)
    A->>P: tx1: продлить удержания на время оплаты, checkout = STARTED, COMMIT
    A->>K: charge(сумма, карта, ключ = id саги)  [~600 мс]
    alt банк отказал
        K-->>A: declined
        A->>P: tx: освободить удержания, FAILED (payment_declined), outbox checkout_failed
        A-->>U: failed — «деньги не списаны, места освобождены»
    else деньги списаны
        K-->>A: succeeded
        A->>P: tx2: checkout = PAID (payment_ref)
        A->>P: tx3: погасить удержания, INSERT sold_seats, заказ, билеты (HMAC-код),<br/>outbox booking.seats_sold + orders.order_paid, COMPLETED
        alt удержания на месте
            A-->>U: completed, order_id
        else удержания истекли / место потеряно
            P-->>A: откат tx3
            A->>K: refund (компенсация)
            A->>P: FAILED (seats_lost), outbox checkout_failed
            A-->>U: failed — «деньги возвращены»
        end
    end

    Note over A,W: Если процесс упал посреди саги (или клиент оборвал запрос),<br/>воркер раз в 60 с находит саги старше 120 с и доводит их:<br/>PAID → дозавершает покупку или возвращает деньги, STARTED → сверяется с банком.
    W->>P: зависшие саги
    W->>K: get_status / refund
    W->>P: COMPLETED или FAILED
```

## 3. События: outbox → RabbitMQ → уведомления

```mermaid
sequenceDiagram
    autonumber
    participant A as API
    participant P as PostgreSQL
    participant R as Воркер: публикатор
    participant Q as RabbitMQ
    participant H as Воркер: уведомления
    participant M as Mailpit (SMTP)

    A->>P: данные + INSERT outbox — одной транзакцией
    loop каждые 0,25 с
        R->>P: SELECT неопубликованные ORDER BY id FOR UPDATE SKIP LOCKED
        R->>Q: publish (publisher confirms) → exchange events, ключ = тип события
        Q-->>R: ack брокера
        R->>P: published_at = now(), COMMIT
    end
    Q->>H: orders.order_paid (очередь notifications)
    H->>P: BEGIN, INSERT processed_messages (consumer, message_id)
    alt уже обработано (повторная доставка)
        H-->>Q: ack, ничего не делаем
    else новое
        H->>P: уведомление в приложении (колокольчик)
        H->>M: письмо с билетами и QR-кодами
        H->>P: COMMIT
        H-->>Q: ack
    end
    Note over H,Q: Ошибка → копия в notifications.retry (TTL 5 с, счётчик x-retries)<br/>→ снова в очередь, после 5 попыток — notifications.dlq.
```

## 4. Схема зала в реальном времени (CQRS + SSE)

```mermaid
sequenceDiagram
    autonumber
    participant B1 as Браузер зрителя
    participant A as API (SSE-хаб)
    participant Rd as Redis
    participant W as Воркер: проектор
    participant Q as RabbitMQ
    participant B2 as Браузер покупателя

    B1->>A: GET /seatmap/status
    A->>Rd: HGET v (версия) → снимок из памяти или HGETALL
    A-->>B1: снимок, version = N
    B1->>A: GET /seatmap/stream (EventSource)
    A->>Rd: PSUBSCRIBE seatmap-live:* (одно подключение на процесс API)
    B2->>A: POST /holds → COMMIT, outbox booking.seats_held
    Note over A,Q: публикатор переносит событие в RabbitMQ (сценарий 3)
    Q->>W: booking.seats_held (очередь seatmap, prefetch=1 — строго по порядку)
    W->>Rd: Lua: HSET место, HINCRBY v → N+1, PUBLISH {v, seats, zones}
    Rd-->>A: сообщение
    A-->>B1: event: delta {v: N+1, seats: {место: "h"}}
    B1->>B1: v = N+1 → применить к снимку, пропуск версии → перечитать снимок
    Note over B1,A: обрыв → браузер переподключается сам (retry 3 с), перечитывает снимок,<br/>без потока — опрос раз в 5 с
```

## 5. Перегрузка: сброс нагрузки на входе

```mermaid
sequenceDiagram
    autonumber
    participant B as Браузер
    participant A as API
    participant P as PostgreSQL

    B->>A: POST /holds (во время наплыва)
    alt одновременных захватов мест < 16
        A->>P: обычная обработка
        A-->>B: 201 / 409
    else очередь полна
        A-->>B: 503 SERVICE_OVERLOADED, Retry-After: 2 (сразу, без работы)
        B->>B: «Очень много покупателей — повторите через пару секунд»
    end
    Note over A: Оплате приоритет: её лимит (40) — лишь предохранитель.<br/>Начатая сага не обрывается: шаги ждут соединение с БД.
```
