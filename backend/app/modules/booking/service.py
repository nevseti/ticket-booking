import uuid
from datetime import UTC, datetime

from app.core.config import settings
from app.core.db import UnitOfWork
from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.booking.repository import HoldRepository, HoldRow
from app.modules.booking.schemas import HoldOut, MyHoldsOut, SeatmapStatus, ZoneAvailability
from app.modules.catalog import facade as catalog
from app.shared.outbox import add_event

# --- Ошибки --------------------------------------------------------------------------------


class EventNotFoundError(NotFoundError):
    code = "EVENT_NOT_FOUND"
    title = "Мероприятие не найдено"


class SalesClosedError(ConflictError):
    code = "SALES_CLOSED"
    title = "Продажи на это мероприятие сейчас закрыты"


class SeatNotFoundError(NotFoundError):
    code = "SEAT_NOT_FOUND"
    title = "Такого места нет"


class SeatNotForSaleError(ConflictError):
    code = "SEAT_NOT_FOR_SALE"
    title = "Это место не продаётся на данное мероприятие"


class UseZoneHoldError(AppError):
    status_code = 422
    code = "USE_ZONE_HOLD"
    title = "Билеты в стоячую зону выбираются количеством, а не местом"


class SeatUnavailableError(ConflictError):
    code = "SEAT_UNAVAILABLE"
    title = "Место уже занято"


class HoldLimitError(ConflictError):
    code = "HOLD_LIMIT"
    title = "Достигнут лимит мест на одно мероприятие"


class ZoneNotFoundError(NotFoundError):
    code = "ZONE_NOT_FOUND"
    title = "Такой стоячей зоны нет"


class NotEnoughPlacesError(ConflictError):
    code = "NOT_ENOUGH_PLACES"
    title = "В зоне не осталось столько свободных мест"


class HoldNotFoundError(NotFoundError):
    code = "HOLD_NOT_FOUND"
    title = "Удержание не найдено или уже истекло"


# --- События (outbox) -------------------------------------------------------------------

SEATS_HELD = "booking.seats_held"
SEATS_RELEASED = "booking.seats_released"
HOLDS_EXPIRED = "booking.holds_expired"


def emit_holds(uow: UnitOfWork, event_type: str, event_id: uuid.UUID, holds: list[HoldRow]) -> None:
    if not holds:
        return
    add_event(
        uow.session,
        event_type,
        event_id,
        {"event_id": str(event_id), "seat_ids": [h.seat_id for h in holds]},
    )


class BookingService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._holds = HoldRepository(uow.session)

    async def _event_on_sale(self, event_id: uuid.UUID) -> catalog.EventInfo:
        event = await catalog.get_event(self._uow, event_id)
        if event is None:
            raise EventNotFoundError()
        if not event.on_sale:
            raise SalesClosedError(extra={"sale_status": event.sale_status})
        return event

    async def _check_limit(self, user_id: uuid.UUID, event_id: uuid.UUID, adding: int) -> None:
        held = await self._holds.count_active(user_id, event_id)
        if held + adding > settings.max_holds_per_event:
            raise HoldLimitError(extra={"limit": settings.max_holds_per_event, "held": held})

    async def hold_seat(self, user_id: uuid.UUID, event_id: uuid.UUID, seat_id: int) -> HoldRow:
        """Удержать сидячее место. Повторный запрос на своё место возвращает то же удержание."""
        event = await self._event_on_sale(event_id)
        seat = (await catalog.get_seats(self._uow, [seat_id])).get(seat_id)
        if seat is None:
            raise SeatNotFoundError()
        if seat.section_kind == catalog.SectionKind.STANDING:
            raise UseZoneHoldError()
        if not event.sells(seat):
            raise SeatNotForSaleError()

        await self._holds.lock_user_event(user_id, event_id)
        existing = await self._holds.active_on_seat(event_id, seat_id)
        if existing and existing.user_id == user_id and existing.expires_at > datetime.now(UTC):
            return existing  # двойной клик не должен превращаться в ошибку
        await self._check_limit(user_id, event_id, adding=1)

        emit_holds(
            self._uow, HOLDS_EXPIRED, event_id, await self._holds.expire_stale(event_id, [seat_id])
        )
        hold = await self._holds.try_capture(event_id, seat_id, user_id, settings.hold_ttl_seconds)
        if hold is None:
            raise SeatUnavailableError()
        emit_holds(self._uow, SEATS_HELD, event_id, [hold])
        return hold

    async def hold_zone(
        self, user_id: uuid.UUID, event_id: uuid.UUID, section_id: int, quantity: int
    ) -> list[HoldRow]:
        """Удержать N билетов в стоячей зоне: занимаются любые свободные места зоны.
        Всё или ничего — при нехватке мест транзакция откатывается целиком."""
        event = await self._event_on_sale(event_id)
        zone = await catalog.get_section(self._uow, section_id)
        if zone is None or zone.kind != catalog.SectionKind.STANDING:
            raise ZoneNotFoundError()
        if event.hall_config not in zone.configs:
            raise SeatNotForSaleError()

        # Порядок блокировок всегда один (пользователь → зона), поэтому они не взаимоблокируются.
        await self._holds.lock_user_event(user_id, event_id)
        await self._check_limit(user_id, event_id, adding=quantity)
        await self._holds.lock_zone(event_id, section_id)
        zone_seats = list(zone.seat_ids)
        emit_holds(
            self._uow, HOLDS_EXPIRED, event_id, await self._holds.expire_stale(event_id, zone_seats)
        )

        acquired: list[HoldRow] = []
        # Кандидатов берём с запасом: на случай, если часть мест прямо сейчас освобождается.
        for _ in range(3):
            need = quantity - len(acquired)
            candidates = await self._holds.free_seats(event_id, zone_seats, limit=need * 3 + 5)
            for seat_id in candidates:
                hold = await self._holds.try_capture(
                    event_id, seat_id, user_id, settings.hold_ttl_seconds
                )
                if hold:
                    acquired.append(hold)
                    if len(acquired) == quantity:
                        break
            if len(acquired) == quantity or not candidates:
                break

        if len(acquired) < quantity:
            available = len(await self._holds.free_seats(event_id, zone_seats, limit=quantity))
            raise NotEnoughPlacesError(extra={"available": available})
        emit_holds(self._uow, SEATS_HELD, event_id, acquired)
        return acquired

    async def release(self, user_id: uuid.UUID, hold_id: uuid.UUID) -> None:
        hold = await self._holds.release(hold_id, user_id)
        if hold is None:
            raise HoldNotFoundError()
        emit_holds(self._uow, SEATS_RELEASED, hold.event_id, [hold])

    async def release_all(self, user_id: uuid.UUID, event_id: uuid.UUID) -> None:
        emit_holds(
            self._uow, SEATS_RELEASED, event_id, await self._holds.release_all(user_id, event_id)
        )

    async def describe(self, event_id: uuid.UUID, holds: list[HoldRow]) -> list[HoldOut]:
        seats = await catalog.get_seats(self._uow, [h.seat_id for h in holds])
        prices = await catalog.get_prices(self._uow, event_id)
        result = []
        for h in holds:
            seat = seats[h.seat_id]
            standing = seat.section_kind == catalog.SectionKind.STANDING
            result.append(
                HoldOut(
                    id=h.id,
                    seat_id=h.seat_id,
                    section_id=seat.section_id,
                    section_name=seat.section_name,
                    standing=standing,
                    row=None if standing else seat.row,
                    number=None if standing else seat.number,
                    category_id=seat.category_id,
                    price_kopecks=prices.get(seat.category_id, 0),
                    expires_at=h.expires_at,
                )
            )
        return result

    async def my_holds(self, user_id: uuid.UUID, event_id: uuid.UUID) -> MyHoldsOut:
        items = await self.describe(event_id, await self._holds.my_active(user_id, event_id))
        return MyHoldsOut(
            items=items,
            total_kopecks=sum(i.price_kopecks for i in items),
            expires_at=min((i.expires_at for i in items), default=None),
            limit=settings.max_holds_per_event,
        )

    async def seatmap_status(self, event_id: uuid.UUID) -> SeatmapStatus:
        held, sold = await self._holds.taken_seats(event_id)
        zones = await catalog.standing_seat_ids(self._uow)
        in_zones = frozenset().union(*zones.values()) if zones else frozenset()
        taken = set(held) | set(sold)
        return SeatmapStatus(
            held=[s for s in held if s not in in_zones],
            sold=[s for s in sold if s not in in_zones],
            zones=[
                ZoneAvailability(
                    section_id=section_id,
                    capacity=len(seat_ids),
                    available=len(seat_ids - taken),
                )
                for section_id, seat_ids in zones.items()
            ],
        )
