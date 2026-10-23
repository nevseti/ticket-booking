import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CheckoutState(StrEnum):
    """Состояния саги оформления заказа."""

    STARTED = "started"  # места подготовлены, идёт оплата
    PAID = "paid"  # банк списал деньги, покупка ещё не зафиксирована
    COMPLETED = "completed"  # заказ создан, места проданы
    FAILED = "failed"  # отказ/ошибка; места освобождены, деньги (если были) возвращены


class Checkout(Base):
    """Сага оплаты. Состояние хранится в БД: после сбоя процесса сагу можно продолжить
    с последнего шага (восстановление выполняет фоновый воркер)."""

    __tablename__ = "checkouts"
    __table_args__ = (
        CheckConstraint("state IN ('started', 'paid', 'completed', 'failed')", name="state"),
        # Повторный запрос с тем же ключом (двойной клик «Оплатить») — та же сага.
        UniqueConstraint("user_id", "idempotency_key"),
        {"schema": "orders"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(16), server_default=CheckoutState.STARTED.value)
    amount_kopecks: Mapped[int] = mapped_column(Integer)
    hold_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    # Снимок позиций на момент оплаты: что именно покупали и по какой цене
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    payment_token: Mapped[str] = mapped_column(String(50))
    payment_ref: Mapped[str | None] = mapped_column(String(100))
    failure_reason: Mapped[str | None] = mapped_column(String(50))
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('paid')", name="status"),  # возвратов в MVP нет
        {"schema": "orders"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    checkout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default="paid")
    total_kopecks: Mapped[int] = mapped_column(Integer)
    payment_ref: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="order", lazy="selectin", order_by="Ticket.section_name, Ticket.row"
    )


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        # Третья линия защиты: на одно место мероприятия — один билет.
        UniqueConstraint("event_id", "seat_id"),
        {"schema": "orders"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.orders.id"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    seat_id: Mapped[int] = mapped_column(Integer)
    section_name: Mapped[str] = mapped_column(String(100))
    row: Mapped[str | None] = mapped_column(String(8))
    number: Mapped[int | None] = mapped_column(Integer)
    standing: Mapped[bool] = mapped_column(Boolean)
    category_name: Mapped[str] = mapped_column(String(50))
    price_kopecks: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(64), unique=True)

    order: Mapped[Order] = relationship(back_populates="tickets")


class MockPayment(Base):
    """Хранилище «банка»-имитатора. Живёт в схеме orders только для простоты: логически
    это внешний сервис, к которому приложение обращается через PaymentGateway."""

    __tablename__ = "mock_payments"
    __table_args__ = (
        CheckConstraint("status IN ('succeeded', 'declined', 'refunded')", name="status"),
        {"schema": "orders"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    amount_kopecks: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
