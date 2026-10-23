import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.core.db import UnitOfWork, get_uow
from app.core.errors import problem_responses
from app.modules.identity.facade import AuthUser, current_user
from app.modules.notifications.models import Notification

router = APIRouter(tags=["notifications"], responses=problem_responses(401))

Uow = Annotated[UnitOfWork, Depends(get_uow)]
User = Annotated[AuthUser, Depends(current_user)]


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    read: bool


class NotificationsOut(BaseModel):
    items: list[NotificationOut]
    unread: int


@router.get("/me/notifications", response_model=NotificationsOut)
async def my_notifications(user: User, uow: Uow) -> NotificationsOut:
    rows = await uow.session.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
    )
    unread = await uow.session.scalar(
        select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return NotificationsOut(
        items=[
            NotificationOut(
                id=n.id,
                kind=n.kind,
                title=n.title,
                body=n.body,
                link=n.link,
                created_at=n.created_at,
                read=n.read_at is not None,
            )
            for n in rows
        ],
        unread=unread or 0,
    )


@router.post("/me/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notifications_read(user: User, uow: Uow) -> None:
    await uow.session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await uow.commit()
