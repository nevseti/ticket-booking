"""Потребитель очереди уведомлений."""

import json
import uuid

import aio_pika
import structlog
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

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
