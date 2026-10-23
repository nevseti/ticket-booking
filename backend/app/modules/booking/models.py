import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class HoldStatus(StrEnum):
    ACTIVE = "active"  # место удержано за пользователем до expires_at
    CONVERTED = "converted"  # удержание погашено покупкой
    RELEASED = "released"  # пользователь отказался от места
    EXPIRED = "expired"  # время удержания вышло


class Hold(Base):
    """Удержание места. Хранится в PostgreSQL, а не в Redis: гарантия «одно место — одно
    активное удержание» обеспечивается ограничением БД и не зависит от кода приложения."""

    __tablename__ = "holds"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'converted', 'released', 'expired')", name="status"),
        # Главная защита от двойного захвата: среди АКТИВНЫХ удержаний пара
        # (мероприятие, место) уникальна. Захват места — одна вставка.
        Index(
            "ux_holds_active_seat",
            "event_id",
            "seat_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        # Уборщик просроченных удержаний
        Index("ix_holds_active_expires", "expires_at", postgresql_where=text("status = 'active'")),
        # «Мои удержания» и лимит мест на пользователя
        Index(
            "ix_holds_active_user",
            "user_id",
            "event_id",
            postgresql_where=text("status = 'active'"),
        ),
        {"schema": "booking"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    seat_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), server_default=HoldStatus.ACTIVE.value)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SoldSeat(Base):
    """Проданное место. Первичный ключ (мероприятие, место) — вторая линия защиты:
    даже если удержание каким-то образом задвоилось, продать место дважды нельзя."""

    __tablename__ = "sold_seats"
    __table_args__ = ({"schema": "booking"},)

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    seat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
