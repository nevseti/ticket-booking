"""Обработчики событий модуля уведомлений (запускаются фоновым воркером).

Модуль ни у кого ничего не спрашивает синхронно, кроме email пользователя: всё нужное для
письма приходит в самом событии (Event-Carried State Transfer).
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.core.db import UnitOfWork
from app.modules.identity import facade as identity
from app.modules.notifications.mailer import Mailer, tickets_email
from app.modules.notifications.models import Notification
from app.shared.inbox import mark_processed

log = structlog.get_logger()

CONSUMER = "notifications"

FAILURE_TEXT = {
    "payment_declined": "Банк отклонил платёж. Деньги не списаны, места освобождены.",
    "payment_unavailable": "Банк не ответил. Деньги не списаны, места освобождены.",
    "seats_lost": "Время удержания мест истекло во время оплаты. Деньги возвращены.",
    "payment_not_confirmed": "Платёж не подтвердился. Деньги не списаны.",
}


def _tickets_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "билет"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "билета"
    return "билетов"


async def on_order_paid(uow: UnitOfWork, payload: dict[str, Any], mailer: Mailer) -> None:
    user_id = uuid.UUID(payload["user_id"])
    count = len(payload.get("tickets", []))
    uow.session.add(
        Notification(
            user_id=user_id,
            kind="order_paid",
            title=f"Оплата прошла: {count} {_tickets_word(count)}",
            body=f"{payload.get('event_title', '')}. Билеты отправлены на почту.",
            link=f"/orders/{payload['order_id']}",
        )
    )
    user = await identity.get_user(uow, user_id)
    if user is not None:
        # Письмо уходит до фиксации транзакции: если SMTP упал — исключение, транзакция
        # откатится, сообщение будет доставлено повторно. Редкий дубль письма при сбое
        # уже после отправки допустим (почта не транзакционна).
        await mailer.send(tickets_email(user.email, user.name, payload))


async def on_checkout_failed(uow: UnitOfWork, payload: dict[str, Any], mailer: Mailer) -> None:
    uow.session.add(
        Notification(
            user_id=uuid.UUID(payload["user_id"]),
            kind="checkout_failed",
            title="Оплата не прошла",
            body=FAILURE_TEXT.get(payload.get("reason", ""), "Попробуйте ещё раз."),
            link=f"/events/{payload['event_id']}",
        )
    )


Handler = Callable[[UnitOfWork, dict[str, Any], Mailer], Awaitable[None]]

HANDLERS: dict[str, Handler] = {
    "orders.order_paid": on_order_paid,
    "orders.checkout_failed": on_checkout_failed,
}


async def handle(
    event_type: str, message_id: uuid.UUID, payload: dict[str, Any], mailer: Mailer
) -> bool:
    """Обработать событие идемпотентно. False — дубликат или неизвестный тип (пропущено)."""
    handler = HANDLERS.get(event_type)
    if handler is None:
        return False
    async with UnitOfWork() as uow:
        if not await mark_processed(uow.session, CONSUMER, message_id):
            log.info("duplicate_skipped", event_type=event_type, message_id=str(message_id))
            return False
        await handler(uow, payload, mailer)
        await uow.commit()
    log.info("notification_handled", event_type=event_type, message_id=str(message_id))
    return True
