"""Подключение к RabbitMQ и топология.

    exchange events          (topic)  — все доменные события; ключ = тип события
    queue notifications      (quorum) ← events: orders.order_paid, orders.checkout_failed
                                      ← events.retry: notifications (возврат после паузы)
    queue notifications.retry         — сообщение, которое не удалось обработать, ждёт
                                        RETRY_DELAY_MS и по TTL возвращается в основную очередь
    queue notifications.dlq           ← events.dlx — после MAX_ATTEMPTS неудачных попыток
    queue seatmap            (classic) ← events: booking.* — проекция схемы зала в Redis

Повторы сделаны явно (счётчик x-retries в заголовке + очередь с TTL): возврат сообщения
через nack(requeue) в quorum-очередь RabbitMQ 4 не увеличивает счётчик доставок, и
«ядовитое» сообщение крутилось бы бесконечно, блокируя очередь.
"""

import asyncio

import aio_pika
import structlog
from aio_pika.abc import AbstractExchange, AbstractRobustConnection

from app.core.config import settings

log = structlog.get_logger()

EXCHANGE = "events"
RETRY_EXCHANGE = "events.retry"
DEAD_LETTER_EXCHANGE = "events.dlx"
MAX_ATTEMPTS = 5
RETRY_DELAY_MS = 5000

# очередь → ключи маршрутизации (типы событий)
QUEUES: dict[str, list[str]] = {
    "notifications": ["orders.order_paid", "orders.checkout_failed"],
}

# Очереди проекций (моделей чтения). Здесь важен порядок событий, поэтому они устроены
# иначе: классическая очередь, один потребитель, по одному сообщению за раз; при сбое
# сообщение возвращается на своё место (requeue), а не в конец через retry-очередь.
PROJECTION_QUEUES: dict[str, list[str]] = {
    "seatmap": [
        "booking.seats_held",
        "booking.seats_released",
        "booking.holds_expired",
        "booking.seats_sold",
    ],
}


def retry_queue(name: str) -> str:
    return f"{name}.retry"


async def connect() -> AbstractRobustConnection:
    """Подключиться с повторами: воркер может стартовать раньше брокера."""
    delay = 1.0
    while True:
        try:
            return await aio_pika.connect_robust(settings.rabbitmq_url)
        except (OSError, aio_pika.exceptions.AMQPConnectionError) as exc:
            log.warning("rabbitmq_unavailable", error=str(exc), retry_in=delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def declare_topology(connection: AbstractRobustConnection) -> AbstractExchange:
    channel = await connection.channel()
    exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    retry = await channel.declare_exchange(
        RETRY_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
    )
    dlx = await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
    )
    for name, routing_keys in QUEUES.items():
        queue = await channel.declare_queue(
            name,
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-delivery-limit": MAX_ATTEMPTS,
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                "x-dead-letter-routing-key": name,
            },
        )
        for key in routing_keys:
            await queue.bind(exchange, key)
        await queue.bind(retry, name)
        await channel.declare_queue(
            retry_queue(name),
            durable=True,
            arguments={
                "x-message-ttl": RETRY_DELAY_MS,
                "x-dead-letter-exchange": RETRY_EXCHANGE,
                "x-dead-letter-routing-key": name,
            },
        )
        dead = await channel.declare_queue(f"{name}.dlq", durable=True)
        await dead.bind(dlx, name)
    for name, routing_keys in PROJECTION_QUEUES.items():
        queue = await channel.declare_queue(
            name, durable=True, arguments={"x-queue-type": "classic"}
        )
        for key in routing_keys:
            await queue.bind(exchange, key)
    await channel.close()
    log.info("rabbitmq_topology_ready", queues=[*QUEUES, *PROJECTION_QUEUES])
    return exchange
