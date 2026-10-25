import uuid
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.modules.catalog.models import EventKind, EventStatus
from app.modules.catalog.venue_layout import HallConfig, SectionKind

MAX_PRICE_KOPECKS = 10_000_000  # 100 000 ₽ за место — разумный потолок от опечаток


class SaleStatus(StrEnum):
    """Состояние продаж, вычисляемое из статуса и окна продаж мероприятия."""

    DRAFT = "draft"
    CANCELLED = "cancelled"
    NOT_STARTED = "not_started"
    ON_SALE = "on_sale"
    ENDED = "ended"


# --- Схема зала ------------------------------------------------------------------------


class CategoryOut(BaseModel):
    id: int
    name: str
    color: str


class SectionOut(BaseModel):
    id: int
    code: str
    name: str
    path: str
    label_x: float
    label_y: float
    kind: SectionKind
    configs: list[HallConfig] = Field(description="Режимы зала, в которых сектор продаётся")
    capacity: int
    category_id: int | None = Field(description="Категория стоячей зоны (у сидячих — у мест)")


class SeatOut(BaseModel):
    id: int
    section_id: int
    row: str
    number: int
    x: float
    y: float
    category_id: int


class RinkOut(BaseModel):
    x: float
    y: float
    width: float
    height: float
    radius: float


class BoxOut(BaseModel):
    """Корпоративная ложа: рисуется на схеме, в продажу не поступает."""

    x: float
    y: float
    width: float
    height: float


class HallConfigOut(BaseModel):
    id: HallConfig
    name: str
    capacity: int
    category_ids: list[int] = Field(description="Ценовые категории, которые есть в этом режиме")


class VenueLayout(BaseModel):
    """Статичная схема площадки: одинакова для всех мероприятий, отлично кэшируется.

    Места стоячих зон в `seats` не входят — у них нет ряда и координат, только вместимость.
    """

    name: str
    address: str
    width: int
    height: int
    rink: RinkOut
    stage_path: str
    boxes: list[BoxOut]
    categories: list[CategoryOut]
    hall_configs: list[HallConfigOut]
    sections: list[SectionOut]
    seats: list[SeatOut]


# --- Мероприятия -------------------------------------------------------------------------


class PriceIn(BaseModel):
    category_id: int = Field(ge=1)
    price_kopecks: int = Field(gt=0, le=MAX_PRICE_KOPECKS)


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    kind: EventKind
    starts_at: AwareDatetime
    sales_start_at: AwareDatetime
    sales_end_at: AwareDatetime | None = Field(
        default=None, description="По умолчанию — момент начала мероприятия"
    )
    poster_url: str | None = Field(
        default=None,
        max_length=500,
        pattern=r"^(https?://|/)\S+$",
        description="Ссылка на картинку (http/https) или путь на сайте (/posters/...)",
    )
    poster_credit: str | None = Field(
        default=None, max_length=300, description="Автор фото и лицензия"
    )
    poster_source: str | None = Field(
        default=None, max_length=500, pattern=r"^https?://\S+$", description="Страница фото"
    )
    prices: list[PriceIn] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым")
        return value

    @model_validator(mode="after")
    def check_dates_and_prices(self) -> Self:
        if self.sales_end_at is None:
            self.sales_end_at = self.starts_at
        if self.sales_start_at >= self.sales_end_at:
            raise ValueError("Продажи должны начинаться раньше, чем заканчиваются")
        if self.sales_end_at > self.starts_at:
            raise ValueError("Продажи должны закончиться не позже начала мероприятия")
        categories = [p.category_id for p in self.prices]
        if len(categories) != len(set(categories)):
            raise ValueError("Цена для каждой категории указывается один раз")
        return self


class PriceOut(BaseModel):
    category_id: int
    category_name: str
    color: str
    price_kopecks: int


class EventCard(BaseModel):
    id: uuid.UUID
    title: str
    kind: EventKind
    hall_config: HallConfig = Field(description="Режим зала: hockey или stage (сцена)")
    starts_at: datetime
    sales_start_at: datetime
    sales_end_at: datetime
    sale_status: SaleStatus
    min_price_kopecks: int | None
    poster_url: str | None
    poster_credit: str | None
    poster_source: str | None


class VenueInfo(BaseModel):
    name: str
    address: str


class EventDetail(EventCard):
    description: str
    prices: list[PriceOut]
    venue: VenueInfo


class AdminEvent(EventDetail):
    status: EventStatus
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
