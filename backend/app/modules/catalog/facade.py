"""Публичный интерфейс модуля catalog. Только его могут вызывать другие модули.

Нужен бронированию (продаются ли билеты, существует ли место) и заказам (цены, подписи мест).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.db import UnitOfWork
from app.modules.catalog.reference import SeatRef, SectionRef, get_reference
from app.modules.catalog.repository import EventRepository
from app.modules.catalog.schemas import SaleStatus
from app.modules.catalog.service import hall_config_for, now_utc, sale_status
from app.modules.catalog.venue_layout import HallConfig, SectionKind

__all__ = [
    "EventInfo",
    "HallConfig",
    "SaleStatus",
    "SeatRef",
    "SectionKind",
    "SectionRef",
    "StandingZones",
    "get_categories",
    "get_event",
    "get_events",
    "get_prices",
    "get_seats",
    "get_section",
    "standing_seat_ids",
    "standing_zones",
]


@dataclass(frozen=True)
class EventInfo:
    id: uuid.UUID
    title: str
    starts_at: datetime
    sale_status: SaleStatus
    hall_config: HallConfig

    @property
    def on_sale(self) -> bool:
        return self.sale_status == SaleStatus.ON_SALE

    def sells(self, seat: SeatRef) -> bool:
        """Продаётся ли место на это мероприятие (зависит от режима зала)."""
        return self.hall_config in seat.configs


async def get_event(uow: UnitOfWork, event_id: uuid.UUID) -> EventInfo | None:
    event = await EventRepository(uow.session).get(event_id)
    if event is None:
        return None
    return EventInfo(
        id=event.id,
        title=event.title,
        starts_at=event.starts_at,
        sale_status=sale_status(event, now_utc()),
        hall_config=hall_config_for(event.kind),
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


async def get_section(uow: UnitOfWork, section_id: int) -> SectionRef | None:
    """Сектор площадки; у стоячей зоны в seat_ids — её безымянные места."""
    ref = await get_reference(uow.session)
    return ref.sections.get(section_id)


async def standing_seat_ids(uow: UnitOfWork) -> dict[int, frozenset[int]]:
    """Стоячие зоны: id сектора → множество id его безымянных мест."""
    ref = await get_reference(uow.session)
    return {
        s.id: frozenset(s.seat_ids) for s in ref.sections.values() if s.kind == SectionKind.STANDING
    }


@dataclass(frozen=True)
class StandingZones:
    """Стоячие зоны в удобном для подсчёта виде."""

    zone_of: dict[int, int]  # id места → id стоячей зоны
    capacity: dict[int, int]  # id зоны → число мест


_zones: tuple[object, StandingZones] | None = None


async def standing_zones(uow: UnitOfWork) -> StandingZones:
    """То же, что standing_seat_ids, но посчитанное один раз на загруженный справочник."""
    global _zones
    ref = await get_reference(uow.session)
    if _zones is None or _zones[0] is not ref:
        zones = await standing_seat_ids(uow)
        _zones = (
            ref,
            StandingZones(
                zone_of={seat: zone for zone, seats in zones.items() for seat in seats},
                capacity={zone: len(seats) for zone, seats in zones.items()},
            ),
        )
    return _zones[1]


async def get_events(uow: UnitOfWork, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, EventInfo]:
    """Несколько мероприятий за раз (для списка заказов)."""
    result = {}
    for event_id in dict.fromkeys(event_ids):
        info = await get_event(uow, event_id)
        if info is not None:
            result[event_id] = info
    return result


async def get_categories(uow: UnitOfWork) -> dict[int, str]:
    """Ценовые категории: id → название."""
    ref = await get_reference(uow.session)
    return {c.id: c.name for c in ref.categories.values()}
