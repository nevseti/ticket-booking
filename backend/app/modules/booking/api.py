import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.db import UnitOfWork, get_uow
from app.core.errors import problem_responses
from app.modules.booking.schemas import HoldOut, HoldSeatIn, HoldZoneIn, MyHoldsOut, SeatmapStatus
from app.modules.booking.service import BookingService
from app.modules.identity.facade import AuthUser, current_user

router = APIRouter(tags=["booking"], responses=problem_responses(422))

Uow = Annotated[UnitOfWork, Depends(get_uow)]
User = Annotated[AuthUser, Depends(current_user)]


@router.post(
    "/events/{event_id}/holds",
    response_model=HoldOut,
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 404, 409),
)
async def hold_seat(event_id: uuid.UUID, body: HoldSeatIn, user: User, uow: Uow) -> HoldOut:
    """Удержать место на 10 минут. 409 SEAT_UNAVAILABLE — место уже занял кто-то другой."""
    service = BookingService(uow)
    hold = await service.hold_seat(user.id, event_id, body.seat_id)
    [result] = await service.describe(event_id, [hold])
    await uow.commit()
    return result


@router.post(
    "/events/{event_id}/holds/zone",
    response_model=list[HoldOut],
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 404, 409),
)
async def hold_zone(event_id: uuid.UUID, body: HoldZoneIn, user: User, uow: Uow) -> list[HoldOut]:
    """Удержать билеты в стоячую зону (Фан-зона, Танцпол) — по количеству."""
    service = BookingService(uow)
    holds = await service.hold_zone(user.id, event_id, body.section_id, body.quantity)
    result = await service.describe(event_id, holds)
    await uow.commit()
    return result


@router.get(
    "/events/{event_id}/holds/my", response_model=MyHoldsOut, responses=problem_responses(401)
)
async def my_holds(event_id: uuid.UUID, user: User, uow: Uow) -> MyHoldsOut:
    return await BookingService(uow).my_holds(user.id, event_id)


@router.delete(
    "/events/{event_id}/holds/my",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(401),
)
async def release_my_holds(event_id: uuid.UUID, user: User, uow: Uow) -> None:
    """Отказаться от всех своих мест на мероприятие."""
    await BookingService(uow).release_all(user.id, event_id)
    await uow.commit()


@router.delete(
    "/holds/{hold_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(401, 404),
)
async def release_hold(hold_id: uuid.UUID, user: User, uow: Uow) -> None:
    await BookingService(uow).release(user.id, hold_id)
    await uow.commit()


@router.get("/events/{event_id}/seatmap/status", response_model=SeatmapStatus)
async def get_seatmap_status(event_id: uuid.UUID, uow: Uow) -> SeatmapStatus:
    """Занятость зала: удержанные и проданные места, остаток в стоячих зонах."""
    return await BookingService(uow).seatmap_status(event_id)
