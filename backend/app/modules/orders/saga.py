"""Сага оформления заказа (Saga с компенсацией).

Оплата — вызов внешнего сервиса, поэтому её нельзя держать внутри транзакции БД
(блокировки, соединение из пула, таймауты). Процесс разбит на короткие локальные
транзакции, состояние которых хранится в orders.checkouts:

    1. start      удержания продлеваются на время оплаты, создаётся checkout(STARTED)
    2. charge     списание в банке — ВНЕ транзакции
    3a. PAID →    покупка ОДНОЙ транзакцией: погасить удержания, создать заказ и билеты,
                  пометить места проданными, записать события → COMPLETED
    3b. отказ →   компенсация: освободить удержания → FAILED
    3c. покупка не удалась после оплаты (удержание истекло, место продано) →
                  компенсация: вернуть деньги и освободить удержания → FAILED

Если процесс упал между шагами, recover() продолжает сагу с сохранённого состояния.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.db import UnitOfWork
from app.core.errors import ConflictError
from app.modules.booking import facade as booking
from app.modules.catalog import facade as catalog
from app.modules.orders.models import Checkout, CheckoutState, Order, Ticket
from app.modules.orders.payments import (
    PaymentGateway,
    PaymentStatus,
    PaymentUnavailableError,
)
from app.modules.orders.tickets import make_code
from app.shared.outbox import add_event

log = structlog.get_logger()

ORDER_PAID = "orders.order_paid"
CHECKOUT_FAILED = "orders.checkout_failed"


class NothingToPayError(ConflictError):
    code = "NOTHING_TO_PAY"
    title = "Нет выбранных мест: удержания истекли или не были выбраны"


class SalesClosedError(ConflictError):
    code = "SALES_CLOSED"
    title = "Продажи на это мероприятие закрыты"


async def _describe_items(
    uow: UnitOfWork, event_id: uuid.UUID, holds: list[booking.CheckoutHold]
) -> list[dict[str, Any]]:
    """Снимок позиций: место, категория и цена на момент оплаты."""
    seats = await catalog.get_seats(uow, [h.seat_id for h in holds])
    prices = await catalog.get_prices(uow, event_id)
    categories = await catalog.get_categories(uow)
    items = []
    for h in holds:
        seat = seats[h.seat_id]
        standing = seat.section_kind == catalog.SectionKind.STANDING
        items.append(
            {
                "hold_id": str(h.hold_id),
                "seat_id": h.seat_id,
                "section_name": seat.section_name,
                "row": None if standing else seat.row,
                "number": None if standing else seat.number,
                "standing": standing,
                "category_name": categories[seat.category_id],
                "price_kopecks": prices[seat.category_id],
            }
        )
    return items


class CheckoutSaga:
    def __init__(self, gateway: PaymentGateway) -> None:
        self._gateway = gateway

    # --- Шаг 1 -----------------------------------------------------------------------

    async def start(
        self,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
        payment_token: str,
        idempotency_key: str,
    ) -> tuple[Checkout, bool]:
        """Создать сагу. Возвращает (checkout, создана_ли_сейчас): повтор запроса с тем же
        ключом идемпотентности отдаёт уже существующую сагу и не платит второй раз."""
        async with UnitOfWork() as uow:
            existing = await uow.session.scalar(
                select(Checkout).where(
                    Checkout.user_id == user_id, Checkout.idempotency_key == idempotency_key
                )
            )
            if existing:
                return existing, False

            event = await catalog.get_event(uow, event_id)
            if event is None or not event.on_sale:
                raise SalesClosedError()
            holds = await booking.prepare_checkout(uow, user_id, event_id)
            if not holds:
                raise NothingToPayError()
            items = await _describe_items(uow, event_id, holds)
            checkout = Checkout(
                user_id=user_id,
                event_id=event_id,
                idempotency_key=idempotency_key,
                state=CheckoutState.STARTED,
                amount_kopecks=sum(i["price_kopecks"] for i in items),
                hold_ids=[h.hold_id for h in holds],
                items=items,
                payment_token=payment_token,
            )
            uow.session.add(checkout)
            await uow.commit()
            await uow.session.refresh(checkout)
            return checkout, True

    # --- Шаги 2–3 ----------------------------------------------------------------------

    async def run(self, checkout_id: uuid.UUID) -> Checkout:
        """Провести сагу до конечного состояния (COMPLETED или FAILED)."""
        checkout = await self._load(checkout_id)
        if checkout.state == CheckoutState.STARTED:
            try:
                result = await self._gateway.charge(
                    checkout.amount_kopecks, checkout.payment_token, str(checkout.id)
                )
            except PaymentUnavailableError:
                return await self._fail(checkout_id, "payment_unavailable", refund=None)
            if result.status != PaymentStatus.SUCCEEDED:
                return await self._fail(checkout_id, "payment_declined", refund=None)
            checkout = await self._mark_paid(checkout_id, result.payment_ref)

        if checkout.state == CheckoutState.PAID:
            try:
                return await self._purchase(checkout_id)
            except (booking.HoldsChangedError, ConflictError) as exc:
                log.warning(
                    "purchase_failed_after_payment", checkout_id=str(checkout_id), error=str(exc)
                )
                return await self._fail(checkout_id, "seats_lost", refund=checkout.payment_ref)
            except Exception:  # IntegrityError и пр.: место успели продать — деньги вернуть
                log.exception("purchase_error", checkout_id=str(checkout_id))
                return await self._fail(checkout_id, "seats_lost", refund=checkout.payment_ref)
        return checkout

    async def recover(self, checkout_id: uuid.UUID) -> Checkout:
        """Продолжить сагу после сбоя. Для STARTED сначала спрашиваем банк: может быть,
        деньги уже списаны, а ответ до нас не дошёл."""
        checkout = await self._load(checkout_id)
        if checkout.state == CheckoutState.STARTED:
            status = await self._gateway.get_status(str(checkout.id))
            if status is None or status.status != PaymentStatus.SUCCEEDED:
                return await self._fail(checkout_id, "payment_not_confirmed", refund=None)
            await self._mark_paid(checkout_id, status.payment_ref)
        return await self.run(checkout_id)

    # --- Транзакции ----------------------------------------------------------------------

    async def _load(self, checkout_id: uuid.UUID) -> Checkout:
        async with UnitOfWork() as uow:
            checkout = await uow.session.get(Checkout, checkout_id)
            assert checkout is not None
            return checkout

    async def _mark_paid(self, checkout_id: uuid.UUID, payment_ref: str) -> Checkout:
        async with UnitOfWork() as uow:
            checkout = await uow.session.get(Checkout, checkout_id, with_for_update=True)
            assert checkout is not None
            if checkout.state == CheckoutState.STARTED:
                checkout.state = CheckoutState.PAID
                checkout.payment_ref = payment_ref
            await uow.commit()
            await uow.session.refresh(checkout)
            return checkout

    async def _purchase(self, checkout_id: uuid.UUID) -> Checkout:
        """Покупка — ОДНА транзакция: погасить удержания, создать заказ и билеты,
        пометить места проданными, записать события. Либо всё, либо ничего."""
        async with UnitOfWork() as uow:
            checkout = await uow.session.get(Checkout, checkout_id, with_for_update=True)
            assert checkout is not None
            if checkout.state != CheckoutState.PAID:
                return checkout  # уже обработано параллельным восстановлением

            order = Order(
                id=uuid.uuid4(),
                user_id=checkout.user_id,
                event_id=checkout.event_id,
                checkout_id=checkout.id,
                total_kopecks=checkout.amount_kopecks,
                payment_ref=checkout.payment_ref or "",
            )
            await booking.confirm_sale(
                uow, checkout.user_id, checkout.event_id, list(checkout.hold_ids), order.id
            )
            uow.session.add(order)
            tickets_payload = []
            for item in checkout.items:
                ticket_id = uuid.uuid4()
                code = make_code(ticket_id)
                tickets_payload.append(
                    {
                        "seat": item["section_name"]
                        + (
                            ", стоячее место"
                            if item["standing"]
                            else f", ряд {item['row']}, место {item['number']}"
                        ),
                        "category": item["category_name"],
                        "price_kopecks": item["price_kopecks"],
                        "code": code,
                    }
                )
                uow.session.add(
                    Ticket(
                        id=ticket_id,
                        order_id=order.id,
                        event_id=checkout.event_id,
                        seat_id=item["seat_id"],
                        section_name=item["section_name"],
                        row=item["row"],
                        number=item["number"],
                        standing=item["standing"],
                        category_name=item["category_name"],
                        price_kopecks=item["price_kopecks"],
                        code=code,
                    )
                )
            checkout.state = CheckoutState.COMPLETED
            checkout.order_id = order.id
            event = await catalog.get_event(uow, checkout.event_id)
            # Событие несёт всё, что нужно для письма (Event-Carried State Transfer):
            # модулю уведомлений не нужно синхронно обращаться к заказам.
            add_event(
                uow.session,
                ORDER_PAID,
                order.id,
                {
                    "order_id": str(order.id),
                    "user_id": str(checkout.user_id),
                    "event_id": str(checkout.event_id),
                    "event_title": event.title if event else "",
                    "event_starts_at": event.starts_at.isoformat() if event else None,
                    "total_kopecks": checkout.amount_kopecks,
                    "tickets": tickets_payload,
                },
            )
            await uow.commit()
            await uow.session.refresh(checkout)
            log.info("order_paid", order_id=str(order.id), tickets=len(checkout.items))
            return checkout

    async def _fail(self, checkout_id: uuid.UUID, reason: str, refund: str | None) -> Checkout:
        """Компенсация: вернуть деньги (если списаны) и освободить удержания."""
        if refund:
            await self._gateway.refund(refund)
        async with UnitOfWork() as uow:
            checkout = await uow.session.get(Checkout, checkout_id, with_for_update=True)
            assert checkout is not None
            if checkout.state in (CheckoutState.COMPLETED, CheckoutState.FAILED):
                return checkout
            await booking.release_holds(uow, checkout.user_id, list(checkout.hold_ids))
            checkout.state = CheckoutState.FAILED
            checkout.failure_reason = reason
            add_event(
                uow.session,
                CHECKOUT_FAILED,
                checkout.id,
                {
                    "checkout_id": str(checkout.id),
                    "user_id": str(checkout.user_id),
                    "event_id": str(checkout.event_id),
                    "reason": reason,
                },
            )
            await uow.commit()
            await uow.session.refresh(checkout)
            log.info("checkout_failed", checkout_id=str(checkout_id), reason=reason)
            return checkout
