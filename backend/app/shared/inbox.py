"""Идемпотентный приём сообщений (Inbox).

Outbox гарантирует доставку «хотя бы один раз»: при сбое между публикацией и отметкой
published_at событие уйдёт повторно. Поэтому обработчик отмечает сообщение как обработанное
в ТОЙ ЖЕ транзакции, что и свой результат: повтор увидит отметку и будет пропущен.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    __table_args__ = ({"schema": "infra"},)

    consumer: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def mark_processed(session: AsyncSession, consumer: str, message_id: uuid.UUID) -> bool:
    """Отметить сообщение обработанным. False — оно уже обрабатывалось (дубликат)."""
    result = await session.execute(
        insert(ProcessedMessage)
        .values(consumer=consumer, message_id=message_id)
        .on_conflict_do_nothing()
        .returning(ProcessedMessage.message_id)
    )
    return result.first() is not None
