"""Публичный интерфейс модуля catalog. Только его могут вызывать другие модули.

Нужен бронированию (продаются ли билеты, существует ли место) и заказам (цены, подписи мест).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.db import UnitOfWork
from app.modules.catalog.reference import SeatRef, get_reference
from app.modules.catalog.repository import EventRepository
from app.modules.catalog.schemas import SaleStatus
from app.modules.catalog.service import now_utc, sale_status

__all__ = ["EventInfo", "SaleStatus", "SeatRef", "get_event", "get_prices", "get_seats"]


@dataclass(frozen=True)
class EventInfo:
    id: uuid.UUID
    title: str
    starts_at: datetime
    sale_status: SaleStatus

    @property
    def on_sale(self) -> bool:
        return self.sale_status == SaleStatus.ON_SALE


async def get_event(uow: UnitOfWork, event_id: uuid.UUID) -> EventInfo | None:
    event = await EventRepository(uow.session).get(event_id)
    if event is None:
        return None
    return EventInfo(
        id=event.id,
        title=event.title,
        starts_at=event.starts_at,
        sale_status=sale_status(event, now_utc()),
    )


async def get_prices(uow: UnitOfWork, event_id: uuid.UUID) -> dict[int, int]:
    """Цены мероприятия: id ценовой категории → цена в копейках."""
    event = await EventRepository(uow.session).get(event_id)
    if event is None:
        return {}
    return {p.price_category_id: p.price_kopecks for p in event.prices}


async def get_seats(uow: UnitOfWork, seat_ids: list[int]) -> dict[int, SeatRef]:
    """Места площадки по id (неизвестные id в ответ не попадают). Из кэша, без запроса к БД."""
    ref = await get_reference(uow.session)
    return {seat_id: ref.seats[seat_id] for seat_id in seat_ids if seat_id in ref.seats}
