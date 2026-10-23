"""Публичный интерфейс модуля orders. Только его могут вызывать другие модули
(и фоновый воркер)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import UnitOfWork
from app.modules.orders.models import Checkout, CheckoutState
from app.modules.orders.payments import get_gateway
from app.modules.orders.saga import CheckoutSaga

__all__ = ["recover_stuck_checkouts"]


async def recover_stuck_checkouts(older_than: timedelta) -> int:
    """Довести до конца саги, «зависшие» в STARTED/PAID (процесс упал посреди оплаты).
    Возвращает число обработанных саг."""
    threshold = datetime.now(UTC) - older_than
    async with UnitOfWork() as uow:
        ids: list[uuid.UUID] = list(
            await uow.session.scalars(
                select(Checkout.id)
                .where(
                    Checkout.state.in_([CheckoutState.STARTED, CheckoutState.PAID]),
                    Checkout.updated_at < threshold,
                )
                .limit(50)
            )
        )
    saga = CheckoutSaga(get_gateway())
    for checkout_id in ids:
        await saga.recover(checkout_id)
    return len(ids)
