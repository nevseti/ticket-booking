"""Публичный интерфейс модуля booking. Только его могут вызывать другие модули.

Нужен заказам (сага оплаты): подготовить удержания к оплате, погасить их покупкой,
освободить при отказе.
"""

import uuid
from dataclasses import dataclass

from app.core.db import UnitOfWork
from app.core.errors import ConflictError
from app.modules.booking.repository import HoldRepository
from app.modules.booking.service import SEATS_RELEASED, emit_holds
from app.shared.outbox import add_event

__all__ = [
    "CheckoutHold",
    "HoldsChangedError",
    "confirm_sale",
    "prepare_checkout",
    "release_holds",
]

SEATS_SOLD = "booking.seats_sold"

# Сколько времени гарантированно держим места на время оплаты
CHECKOUT_HOLD_SECONDS = 3 * 60


class HoldsChangedError(ConflictError):
    code = "HOLDS_CHANGED"
    title = "Часть мест больше не удерживается за вами"


@dataclass(frozen=True)
class CheckoutHold:
    hold_id: uuid.UUID
    seat_id: int


async def prepare_checkout(
    uow: UnitOfWork, user_id: uuid.UUID, event_id: uuid.UUID
) -> list[CheckoutHold]:
    """Активные удержания пользователя на мероприятие, продлённые на время оплаты."""
    holds = await HoldRepository(uow.session).extend_for_checkout(
        user_id, event_id, CHECKOUT_HOLD_SECONDS
    )
    return [CheckoutHold(h.id, h.seat_id) for h in holds]


async def confirm_sale(
    uow: UnitOfWork,
    user_id: uuid.UUID,
    event_id: uuid.UUID,
    hold_ids: list[uuid.UUID],
    order_id: uuid.UUID,
) -> list[int]:
    """Часть транзакции покупки: погасить удержания и пометить места проданными.

    Если хоть одно удержание уже не активно (истекло, освобождено) — HoldsChangedError,
    и вызывающая транзакция откатывается целиком. Возвращает проданные места.
    """
    repo = HoldRepository(uow.session)
    converted = await repo.convert(user_id, hold_ids)
    if len(converted) != len(hold_ids):
        raise HoldsChangedError()
    seat_ids = [h.seat_id for h in converted]
    await repo.mark_sold(event_id, seat_ids, order_id)
    add_event(
        uow.session,
        SEATS_SOLD,
        event_id,
        {"event_id": str(event_id), "seat_ids": seat_ids, "order_id": str(order_id)},
    )
    return seat_ids


async def release_holds(uow: UnitOfWork, user_id: uuid.UUID, hold_ids: list[uuid.UUID]) -> None:
    """Компенсация саги: отпустить удержания (если они ещё активны)."""
    released = await HoldRepository(uow.session).release_many(user_id, hold_ids)
    if released:
        emit_holds(uow, SEATS_RELEASED, released[0].event_id, released)
