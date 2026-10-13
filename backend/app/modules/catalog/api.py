import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.db import UnitOfWork, get_uow
from app.core.errors import problem_responses
from app.modules.catalog.models import EventKind, EventStatus
from app.modules.catalog.reference import get_reference
from app.modules.catalog.repository import EventFilters
from app.modules.catalog.schemas import (
    AdminEvent,
    EventCard,
    EventDetail,
    EventIn,
    Page,
    VenueLayout,
)
from app.modules.catalog.service import (
    CatalogService,
    EventNotFoundError,
    now_utc,
    to_admin,
    to_card,
    to_detail,
)
from app.modules.identity.facade import AuthUser, optional_user, require_admin

Uow = Annotated[UnitOfWork, Depends(get_uow)]

router = APIRouter(tags=["catalog"], responses=problem_responses(422))
admin_router = APIRouter(
    prefix="/admin",
    tags=["catalog-admin"],
    dependencies=[Depends(require_admin)],
    responses=problem_responses(401, 403, 422),
)

LAYOUT_CACHE_CONTROL = "public, max-age=300"


# --- Публичная часть -------------------------------------------------------------------


@router.get("/venue/layout", response_model=VenueLayout)
async def get_venue_layout(request: Request, uow: Uow) -> Response:
    """Схема зала: секторы, места, ценовые категории. Поддерживает ETag (304 Not Modified)."""
    ref = await get_reference(uow.session)
    headers = {"ETag": ref.etag, "Cache-Control": LAYOUT_CACHE_CONTROL}
    if request.headers.get("if-none-match") == ref.etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=ref.layout_json, media_type="application/json", headers=headers)


@router.get("/events", response_model=Page[EventCard])
async def list_events(
    uow: Uow,
    kind: EventKind | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Поиск по названию")] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    include_past: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 12,
) -> Page[EventCard]:
    """Афиша: опубликованные мероприятия по дате начала."""
    now = now_utc()
    filters = EventFilters(
        kind=kind,
        query=q.strip() if q else None,
        date_from=date_from,
        date_to=date_to,
        starts_after=None if include_past else now,
    )
    events, total = await CatalogService(uow).list_events(filters, page=page, page_size=page_size)
    return Page[EventCard](
        items=[to_card(e, now) for e in events], total=total, page=page, page_size=page_size
    )


@router.get("/events/{event_id}", response_model=EventDetail, responses=problem_responses(404))
async def get_event(
    event_id: uuid.UUID,
    uow: Uow,
    viewer: Annotated[AuthUser | None, Depends(optional_user)],
) -> EventDetail:
    service = CatalogService(uow)
    event = await service.get_event(event_id)
    # Черновик видит только администратор; для остальных его не существует.
    if event.status == EventStatus.DRAFT and not (viewer and viewer.is_admin):
        raise EventNotFoundError()
    return to_detail(event, await service.reference(), now_utc())


# --- Администрирование -----------------------------------------------------------------


@admin_router.get("/events", response_model=Page[AdminEvent])
async def admin_list_events(
    uow: Uow,
    event_status: Annotated[EventStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[AdminEvent]:
    service = CatalogService(uow)
    statuses = (event_status,) if event_status else tuple(EventStatus)
    filters = EventFilters(statuses=statuses, query=q.strip() if q else None)
    events, total = await service.list_events(
        filters, page=page, page_size=page_size, newest_first=True
    )
    ref, now = await service.reference(), now_utc()
    return Page[AdminEvent](
        items=[to_admin(e, ref, now) for e in events], total=total, page=page, page_size=page_size
    )


@admin_router.get("/events/{event_id}", response_model=AdminEvent, responses=problem_responses(404))
async def admin_get_event(event_id: uuid.UUID, uow: Uow) -> AdminEvent:
    service = CatalogService(uow)
    return to_admin(await service.get_event(event_id), await service.reference(), now_utc())


@admin_router.post("/events", response_model=AdminEvent, status_code=status.HTTP_201_CREATED)
async def admin_create_event(body: EventIn, uow: Uow) -> AdminEvent:
    """Создать мероприятие в статусе «черновик»."""
    service = CatalogService(uow)
    event = await service.create_event(body)
    result = to_admin(event, await service.reference(), now_utc())
    await uow.commit()
    return result


@admin_router.put(
    "/events/{event_id}", response_model=AdminEvent, responses=problem_responses(404, 409)
)
async def admin_update_event(event_id: uuid.UUID, body: EventIn, uow: Uow) -> AdminEvent:
    service = CatalogService(uow)
    event = await service.update_event(event_id, body)
    result = to_admin(event, await service.reference(), now_utc())
    await uow.commit()
    return result


@admin_router.post(
    "/events/{event_id}/publish", response_model=AdminEvent, responses=problem_responses(404, 409)
)
async def admin_publish_event(event_id: uuid.UUID, uow: Uow) -> AdminEvent:
    """Опубликовать: мероприятие появится в афише. Нужны цены для всех категорий."""
    service = CatalogService(uow)
    event = await service.publish(event_id)
    result = to_admin(event, await service.reference(), now_utc())
    await uow.commit()
    return result


@admin_router.post(
    "/events/{event_id}/cancel", response_model=AdminEvent, responses=problem_responses(404)
)
async def admin_cancel_event(event_id: uuid.UUID, uow: Uow) -> AdminEvent:
    """Отменить мероприятие: продажи прекращаются."""
    service = CatalogService(uow)
    event = await service.cancel(event_id)
    result = to_admin(event, await service.reference(), now_utc())
    await uow.commit()
    return result
