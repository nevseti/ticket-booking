import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class HoldSeatIn(BaseModel):
    seat_id: int


class HoldZoneIn(BaseModel):
    section_id: int = Field(description="Стоячая зона (Фан-зона, Танцпол)")
    quantity: int = Field(ge=1, le=10)


class HoldOut(BaseModel):
    id: uuid.UUID
    seat_id: int
    section_id: int
    section_name: str
    standing: bool = Field(description="Билет в стоячую зону: без ряда и номера места")
    row: str | None
    number: int | None
    category_id: int
    price_kopecks: int
    expires_at: datetime


class MyHoldsOut(BaseModel):
    items: list[HoldOut]
    total_kopecks: int
    expires_at: datetime | None = Field(description="Когда истечёт первое из удержаний")
    limit: int = Field(description="Сколько мест можно держать на одно мероприятие")


class ZoneAvailability(BaseModel):
    section_id: int
    capacity: int
    available: int


class SeatmapStatus(BaseModel):
    """Занятость зала из модели чтения в Redis (CQRS). Изменения приходят по SSE
    (`/seatmap/stream`) с версиями: изменение с версией version + 1 применяется к этому
    снимку, при пропуске версии снимок нужно перечитать."""

    version: int = Field(description="Версия снимка; 0 — снимок без версии (прямо из БД)")
    held: list[int] = Field(description="Сидячие места, удержанные сейчас")
    sold: list[int] = Field(description="Проданные сидячие места")
    zones: list[ZoneAvailability]
