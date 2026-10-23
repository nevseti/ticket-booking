import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.orders.models import CheckoutState


class CheckoutIn(BaseModel):
    event_id: uuid.UUID
    payment_token: str = Field(
        description="Тестовая карта банка-имитатора: tok_ok, tok_decline, tok_timeout",
        pattern="^tok_(ok|decline|timeout)$",
    )


class CheckoutOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    state: CheckoutState
    amount_kopecks: int
    failure_reason: str | None = Field(
        description="payment_declined, payment_unavailable, seats_lost, payment_not_confirmed"
    )
    order_id: uuid.UUID | None


class TicketOut(BaseModel):
    id: uuid.UUID
    section_name: str
    row: str | None
    number: int | None
    standing: bool
    category_name: str
    price_kopecks: int
    code: str = Field(description="Подписанный код для QR")


class OrderSummary(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    event_title: str
    event_starts_at: datetime
    total_kopecks: int
    tickets_count: int
    created_at: datetime


class OrderDetail(OrderSummary):
    tickets: list[TicketOut]


class TicketCheck(BaseModel):
    valid: bool
    event_title: str | None = None
    event_starts_at: datetime | None = None
    seat: str | None = None
