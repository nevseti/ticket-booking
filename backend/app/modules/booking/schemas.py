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
    """Занятость зала. Временная версия — читается из PostgreSQL; на этапе 7 её заменит
    модель чтения в Redis с обновлением в реальном времени (CQRS + SSE)."""

    held: list[int] = Field(description="Сидячие места, удержанные сейчас")
    sold: list[int] = Field(description="Проданные сидячие места")
    zones: list[ZoneAvailability]
