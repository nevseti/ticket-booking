"""Публикатор outbox: переносит события из infra.outbox в RabbitMQ.

Гарантия — «хотя бы один раз»: событие помечается опубликованным только после
подтверждения брокера (publisher confirms). Если процесс упадёт между публикацией и
отметкой, событие уйдёт повторно — поэтому обработчики идемпотентны (infra.processed_messages).
"""

import json
from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractChannel
from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.core.db import UnitOfWork
from app.shared.outbox import OutboxMessage
from worker.rabbit import EXCHANGE


class Publisher(Protocol):
    async def publish(self, routing_key: str, body: bytes, message_id: str) -> None: ...


class RabbitPublisher:
    def __init__(self, channel: AbstractChannel) -> None:
        self._channel = channel

    async def publish(self, routing_key: str, body: bytes, message_id: str) -> None:
        exchange = await self._channel.get_exchange(EXCHANGE)
        # Канал открыт с publisher confirms: await вернётся, когда брокер принял сообщение.
        await exchange.publish(
            aio_pika.Message(
                body,
                message_id=message_id,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                type=routing_key,
            ),
            routing_key=routing_key,
        )


async def publish_batch(publisher: Publisher, limit: int = 100) -> int:
    """Опубликовать пачку неотправленных событий по порядку. Возвращает их число.

    FOR UPDATE SKIP LOCKED позволяет запустить несколько воркеров: каждый берёт свою пачку.
    """
    async with UnitOfWork() as uow:
        rows = list(
            await uow.session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.published_at.is_(None))
                .order_by(OutboxMessage.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        if not rows:
            return 0
        for row in rows:
            body = json.dumps(
                {
                    "event_id": str(row.event_id),
                    "event_type": row.event_type,
                    "occurred_at": row.occurred_at.isoformat(),
                    "payload": row.payload,
                },
                ensure_ascii=False,
            ).encode()
            await publisher.publish(row.event_type, body, str(row.event_id))
        await uow.session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id.in_([r.id for r in rows]))
            .values(published_at=func.now())
        )
        await uow.commit()
        return len(rows)
