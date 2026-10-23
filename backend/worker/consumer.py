"""Потребители очередей: уведомления (с повторами и DLQ) и проекции (строго по порядку)."""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
import structlog
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from redis.exceptions import RedisError

from app.modules.notifications.handlers import handle
from app.modules.notifications.mailer import Mailer
from worker.rabbit import MAX_ATTEMPTS, retry_queue

log = structlog.get_logger()

QUEUE = "notifications"


async def consume_notifications(connection: AbstractRobustConnection, mailer: Mailer) -> None:
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue = await channel.get_queue(QUEUE)

    async def on_message(message: AbstractIncomingMessage) -> None:
        try:
            envelope = json.loads(message.body)
            await handle(
                envelope["event_type"],
                uuid.UUID(envelope["event_id"]),
                envelope["payload"],
                mailer,
            )
            await message.ack()
        except Exception:
            attempt = int((message.headers or {}).get("x-retries", 0)) + 1
            if attempt >= MAX_ATTEMPTS:
                # Сдаёмся: reject без возврата → RabbitMQ перекладывает в notifications.dlq,
                # где сообщение можно разобрать вручную. Очередь не блокируется.
                log.exception("notification_dead_lettered", message_id=message.message_id)
                await message.reject(requeue=False)
                return
            log.exception("notification_failed", message_id=message.message_id, attempt=attempt)
            # Повтор через паузу: копия уходит в retry-очередь с TTL, оригинал подтверждается.
            await channel.default_exchange.publish(
                aio_pika.Message(
                    message.body,
                    message_id=message.message_id,
                    content_type=message.content_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers={"x-retries": attempt},
                ),
                routing_key=retry_queue(QUEUE),
            )
            await message.ack()

    await queue.consume(on_message)
    log.info("consumer_started", queue=QUEUE)


Projector = Callable[[str, dict[str, Any]], Awaitable[object]]

PROJECTION_RETRY_SECONDS = 1.0


async def consume_projection(
    connection: AbstractRobustConnection, queue_name: str, project: Projector
) -> None:
    """Проекция применяет события строго по порядку: prefetch=1, одно сообщение за раз.
    Если Redis недоступен — пауза и возврат сообщения на его же место: проекция ждёт
    Redis, а не перескакивает через событие."""
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.get_queue(queue_name)

    async def on_message(message: AbstractIncomingMessage) -> None:
        try:
            envelope = json.loads(message.body)
            event_type, payload = envelope["event_type"], envelope["payload"]
        except (ValueError, KeyError):
            log.exception("projection_bad_message", queue=queue_name)
            await message.reject(requeue=False)
            return
        try:
            await project(event_type, payload)
        except (RedisError, OSError) as exc:
            log.warning("projection_store_unavailable", queue=queue_name, error=str(exc))
            await asyncio.sleep(PROJECTION_RETRY_SECONDS)
            await message.nack(requeue=True)
            return
        await message.ack()

    await queue.consume(on_message)
    log.info("consumer_started", queue=queue_name)
