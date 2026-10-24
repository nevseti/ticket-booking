import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select

from app.core import admission
from app.core.db import UnitOfWork, get_uow
from app.core.errors import NotFoundError, problem_responses
from app.core.ratelimit import CHECKOUT, TICKET_VERIFY, limit_by_ip
from app.modules.catalog import facade as catalog
from app.modules.identity.facade import AuthUser, current_user, limit_by_user
from app.modules.orders.models import Checkout, Order, Ticket
from app.modules.orders.payments import PaymentGateway, get_gateway
from app.modules.orders.saga import CheckoutSaga
from app.modules.orders.schemas import (
    CheckoutIn,
    CheckoutOut,
    OrderDetail,
    OrderSummary,
    TicketCheck,
    TicketOut,
)
from app.modules.orders.tickets import parse_code

router = APIRouter(tags=["orders"], responses=problem_responses(422))

Uow = Annotated[UnitOfWork, Depends(get_uow)]
User = Annotated[AuthUser, Depends(current_user)]
Gateway = Annotated[PaymentGateway, Depends(get_gateway)]


class CheckoutNotFoundError(NotFoundError):
    code = "CHECKOUT_NOT_FOUND"
    title = "Оформление не найдено"


class OrderNotFoundError(NotFoundError):
    code = "ORDER_NOT_FOUND"
    title = "Заказ не найден"


def _checkout_out(c: Checkout) -> CheckoutOut:
    return CheckoutOut(
        id=c.id,
        event_id=c.event_id,
        state=c.state,
        amount_kopecks=c.amount_kopecks,
        failure_reason=c.failure_reason,
        order_id=c.order_id,
    )


@router.post(
    "/checkout",
    response_model=CheckoutOut,
    responses=problem_responses(401, 409, 429, 503),
    dependencies=[admission.CHECKOUT.dependency(), limit_by_user(CHECKOUT)],
)
async def checkout(
    body: CheckoutIn,
    user: User,
    gateway: Gateway,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=100,
            description="Уникален для попытки оплаты: повтор запроса не спишет деньги дважды",
        ),
    ],
) -> CheckoutOut:
    """Оплатить удержанные места (сага с компенсацией). Возвращает итог: completed с
    order_id или failed с причиной — при отказе банка места освобождаются."""
    saga = CheckoutSaga(gateway)
    started, created = await saga.start(user.id, body.event_id, body.payment_token, idempotency_key)
    if not created and started.state in ("completed", "failed"):
        return _checkout_out(started)
    return _checkout_out(await saga.run(started.id))


@router.get(
    "/checkout/{checkout_id}", response_model=CheckoutOut, responses=problem_responses(401, 404)
)
async def get_checkout(checkout_id: uuid.UUID, user: User, uow: Uow) -> CheckoutOut:
    checkout = await uow.session.get(Checkout, checkout_id)
    if checkout is None or checkout.user_id != user.id:
        raise CheckoutNotFoundError()
    return _checkout_out(checkout)


async def _summaries(uow: UnitOfWork, orders: list[Order]) -> list[OrderSummary]:
    events = await catalog.get_events(uow, [o.event_id for o in orders])
    return [
        OrderSummary(
            id=o.id,
            event_id=o.event_id,
            event_title=events[o.event_id].title if o.event_id in events else "Мероприятие",
            event_starts_at=events[o.event_id].starts_at if o.event_id in events else o.created_at,
            total_kopecks=o.total_kopecks,
            tickets_count=len(o.tickets),
            created_at=o.created_at,
        )
        for o in orders
    ]


@router.get("/me/orders", response_model=list[OrderSummary], responses=problem_responses(401))
async def my_orders(user: User, uow: Uow) -> list[OrderSummary]:
    orders = await uow.session.scalars(
        select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
    )
    return await _summaries(uow, list(orders))


@router.get("/orders/{order_id}", response_model=OrderDetail, responses=problem_responses(401, 404))
async def get_order(order_id: uuid.UUID, user: User, uow: Uow) -> OrderDetail:
    order = await uow.session.get(Order, order_id)
    if order is None or order.user_id != user.id:
        raise OrderNotFoundError()  # чужой заказ неотличим от несуществующего
    [summary] = await _summaries(uow, [order])
    return OrderDetail(
        **summary.model_dump(),
        tickets=[
            TicketOut(
                id=t.id,
                section_name=t.section_name,
                row=t.row,
                number=t.number,
                standing=t.standing,
                category_name=t.category_name,
                price_kopecks=t.price_kopecks,
                code=t.code,
            )
            for t in order.tickets
        ],
    )


@router.get(
    "/tickets/verify",
    response_model=TicketCheck,
    responses=problem_responses(429),
    dependencies=[limit_by_ip(TICKET_VERIFY)],
)
async def verify_ticket(code: Annotated[str, Query(max_length=100)], uow: Uow) -> TicketCheck:
    """Проверка билета на входе (контролёр сканирует QR): подпись и наличие в БД."""
    ticket_id = parse_code(code)
    ticket = await uow.session.get(Ticket, ticket_id) if ticket_id else None
    if ticket is None:
        return TicketCheck(valid=False)
    event = await catalog.get_event(uow, ticket.event_id)
    seat = (
        f"{ticket.section_name}, стоячие места"
        if ticket.standing
        else f"{ticket.section_name}, ряд {ticket.row}, место {ticket.number}"
    )
    return TicketCheck(
        valid=True,
        event_title=event.title if event else None,
        event_starts_at=event.starts_at if event else None,
        seat=seat,
    )
