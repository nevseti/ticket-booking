import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Event, EventStatus, PriceCategory, Seat, Section, Venue


@dataclass(frozen=True)
class EventFilters:
    kind: str | None = None
    query: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    statuses: tuple[str, ...] = (EventStatus.PUBLISHED,)
    starts_after: datetime | None = None  # для афиши: только будущие


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, event_id: uuid.UUID, *, for_update: bool = False) -> Event | None:
        return await self._session.get(Event, event_id, with_for_update=for_update)

    async def add(self, event: Event) -> Event:
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)  # серверные значения: id, created_at, status
        return event

    def _filtered(self, filters: EventFilters) -> Select[tuple[Event]]:
        stmt = select(Event).where(Event.status.in_(filters.statuses))
        if filters.kind:
            stmt = stmt.where(Event.kind == filters.kind)
        if filters.query:
            stmt = stmt.where(Event.title.ilike(f"%{filters.query}%"))
        if filters.date_from:
            stmt = stmt.where(Event.starts_at >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(Event.starts_at < filters.date_to)
        if filters.starts_after:
            stmt = stmt.where(Event.starts_at >= filters.starts_after)
        return stmt

    async def list(
        self, filters: EventFilters, *, offset: int, limit: int, newest_first: bool = False
    ) -> tuple[list[Event], int]:
        stmt = self._filtered(filters)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        order = Event.starts_at.desc() if newest_first else Event.starts_at.asc()
        rows = await self._session.scalars(
            stmt.order_by(order, Event.id).offset(offset).limit(limit)
        )
        return list(rows), total or 0


class VenueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_venue(self) -> Venue | None:
        return await self._session.scalar(select(Venue).order_by(Venue.id).limit(1))

    async def categories(self) -> list[PriceCategory]:
        return list(await self._session.scalars(select(PriceCategory).order_by(PriceCategory.id)))

    async def sections(self) -> list[Section]:
        return list(await self._session.scalars(select(Section).order_by(Section.sort_order)))

    async def seats(self) -> list[Seat]:
        return list(await self._session.scalars(select(Seat).order_by(Seat.id)))
