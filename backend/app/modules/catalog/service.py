import uuid
from datetime import UTC, datetime

from app.core.db import UnitOfWork
from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.catalog.models import Event, EventKind, EventPrice, EventStatus
from app.modules.catalog.reference import ReferenceData, get_reference
from app.modules.catalog.repository import EventFilters, EventRepository
from app.modules.catalog.schemas import (
    AdminEvent,
    EventCard,
    EventDetail,
    EventIn,
    PriceOut,
    SaleStatus,
    VenueInfo,
)
from app.modules.catalog.venue_layout import HallConfig


class EventNotFoundError(NotFoundError):
    code = "EVENT_NOT_FOUND"
    title = "Мероприятие не найдено"


class EventCancelledError(ConflictError):
    code = "EVENT_CANCELLED"
    title = "Мероприятие отменено"


class PricesIncompleteError(ConflictError):
    code = "PRICES_INCOMPLETE"
    title = "Перед публикацией задайте цены для всех категорий мест"


class UnknownPriceCategoryError(AppError):
    status_code = 422
    code = "UNKNOWN_PRICE_CATEGORY"
    title = "Такой ценовой категории нет в выбранном режиме зала"


def now_utc() -> datetime:
    return datetime.now(UTC)


def hall_config_for(kind: str) -> HallConfig:
    """Хоккей — трибуны вокруг льда; концерты и шоу — сцена, фан-зона и танцпол."""
    return HallConfig.HOCKEY if kind == EventKind.SPORT else HallConfig.STAGE


def sale_status(event: Event, now: datetime) -> SaleStatus:
    if event.status == EventStatus.DRAFT:
        return SaleStatus.DRAFT
    if event.status == EventStatus.CANCELLED:
        return SaleStatus.CANCELLED
    if now < event.sales_start_at:
        return SaleStatus.NOT_STARTED
    if now >= event.sales_end_at:
        return SaleStatus.ENDED
    return SaleStatus.ON_SALE


def _card_fields(event: Event, now: datetime) -> dict:
    prices = [p.price_kopecks for p in event.prices]
    return {
        "id": event.id,
        "title": event.title,
        "kind": event.kind,
        "hall_config": hall_config_for(event.kind),
        "starts_at": event.starts_at,
        "sales_start_at": event.sales_start_at,
        "sales_end_at": event.sales_end_at,
        "sale_status": sale_status(event, now),
        "min_price_kopecks": min(prices) if prices else None,
        "poster_url": event.poster_url,
        "poster_credit": event.poster_credit,
        "poster_source": event.poster_source,
    }


def to_card(event: Event, now: datetime) -> EventCard:
    return EventCard(**_card_fields(event, now))


def _detail_fields(event: Event, ref: ReferenceData, now: datetime) -> dict:
    return {
        **_card_fields(event, now),
        "description": event.description,
        "prices": [
            PriceOut(
                category_id=p.price_category_id,
                category_name=ref.categories[p.price_category_id].name,
                color=ref.categories[p.price_category_id].color,
                price_kopecks=p.price_kopecks,
            )
            for p in event.prices
        ],
        "venue": VenueInfo(name=ref.layout.name, address=ref.layout.address),
    }


def to_detail(event: Event, ref: ReferenceData, now: datetime) -> EventDetail:
    return EventDetail(**_detail_fields(event, ref, now))


def to_admin(event: Event, ref: ReferenceData, now: datetime) -> AdminEvent:
    return AdminEvent(
        **_detail_fields(event, ref, now),
        status=event.status,
        created_at=event.created_at,
        updated_at=event.updated_at,
        published_at=event.published_at,
    )


class CatalogService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._events = EventRepository(uow.session)

    async def reference(self) -> ReferenceData:
        return await get_reference(self._uow.session)

    async def get_event(self, event_id: uuid.UUID, *, for_update: bool = False) -> Event:
        event = await self._events.get(event_id, for_update=for_update)
        if event is None:
            raise EventNotFoundError()
        return event

    async def _validate_prices(self, data: EventIn) -> None:
        ref = await self.reference()
        allowed = ref.config_categories[hall_config_for(data.kind)]
        unknown = [p.category_id for p in data.prices if p.category_id not in allowed]
        if unknown:
            raise UnknownPriceCategoryError(
                extra={"category_ids": unknown, "allowed_category_ids": sorted(allowed)}
            )

    @staticmethod
    def _apply(event: Event, data: EventIn) -> None:
        event.title = data.title
        event.description = data.description
        event.kind = data.kind
        event.starts_at = data.starts_at
        event.sales_start_at = data.sales_start_at
        event.sales_end_at = data.sales_end_at or data.starts_at
        event.poster_url = data.poster_url
        event.poster_credit = data.poster_credit
        event.poster_source = data.poster_source
        event.prices = [
            EventPrice(price_category_id=p.category_id, price_kopecks=p.price_kopecks)
            for p in data.prices
        ]

    async def create_event(self, data: EventIn) -> Event:
        await self._validate_prices(data)
        event = Event()
        self._apply(event, data)
        return await self._events.add(event)

    async def update_event(self, event_id: uuid.UUID, data: EventIn) -> Event:
        await self._validate_prices(data)
        event = await self.get_event(event_id, for_update=True)
        if event.status == EventStatus.CANCELLED:
            raise EventCancelledError()
        self._apply(event, data)
        await self._uow.session.flush()
        await self._uow.session.refresh(event)
        return event

    async def publish(self, event_id: uuid.UUID) -> Event:
        event = await self.get_event(event_id, for_update=True)
        if event.status == EventStatus.CANCELLED:
            raise EventCancelledError()
        if event.status == EventStatus.PUBLISHED:
            return event  # повторная публикация — не ошибка
        ref = await self.reference()
        required = ref.config_categories[hall_config_for(event.kind)]
        missing = sorted(required - {p.price_category_id for p in event.prices})
        if missing:
            raise PricesIncompleteError(extra={"missing_category_ids": missing})
        event.status = EventStatus.PUBLISHED
        event.published_at = now_utc()
        await self._uow.session.flush()
        await self._uow.session.refresh(event)
        return event

    async def cancel(self, event_id: uuid.UUID) -> Event:
        event = await self.get_event(event_id, for_update=True)
        event.status = EventStatus.CANCELLED
        await self._uow.session.flush()
        await self._uow.session.refresh(event)
        return event

    async def list_events(
        self, filters: EventFilters, *, page: int, page_size: int, newest_first: bool = False
    ) -> tuple[list[Event], int]:
        return await self._events.list(
            filters, offset=(page - 1) * page_size, limit=page_size, newest_first=newest_first
        )
