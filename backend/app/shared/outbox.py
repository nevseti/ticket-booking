"""Transactional Outbox: доменное событие записывается в таблицу той же транзакцией,
что и изменение данных. Публикацией в RabbitMQ занимается фоновый воркер (этап 6).

Так событие не теряется и не появляется «лишним»: если транзакция откатилась —
откатилась и запись события; если зафиксировалась — воркер рано или поздно его отправит.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class OutboxMessage(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        # Публикатор выбирает неопубликованные события по порядку записи.
        Index("ix_outbox_unpublished", "id", postgresql_where=text("published_at IS NULL")),
        {"schema": "infra"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=text("uuidv7()"), unique=True
    )
    event_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def add_event(
    session: AsyncSession, event_type: str, aggregate_id: object, payload: dict[str, Any]
) -> None:
    """Добавить событие в outbox текущей транзакции (фиксируется вместе с ней)."""
    session.add(
        OutboxMessage(event_type=event_type, aggregate_id=str(aggregate_id), payload=payload)
    )
