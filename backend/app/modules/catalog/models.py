import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

# Справочные данные площадки: засеваются один раз и не меняются в работе системы.
# Тесты не очищают такие таблицы между прогонами (см. tests/conftest.py).
REFERENCE = {"reference_data": True}


class EventKind(StrEnum):
    """Тип мероприятия. Ледовая арена принимает концерты, шоу и хоккей — театра нет."""

    CONCERT = "concert"
    SHOW = "show"
    SPORT = "sport"


class EventStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class Venue(Base):
    __tablename__ = "venues"
    __table_args__ = ({"schema": "catalog", "info": REFERENCE},)

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300))
    width: Mapped[int] = mapped_column(Integer)  # размеры области схемы (viewBox SVG)
    height: Mapped[int] = mapped_column(Integer)
    stage_path: Mapped[str] = mapped_column(Text)  # контур сцены, SVG path
    # Ледовая площадка (скруглённый прямоугольник) — для отрисовки разметки на хоккее.
    rink_x: Mapped[float] = mapped_column(Float)
    rink_y: Mapped[float] = mapped_column(Float)
    rink_width: Mapped[float] = mapped_column(Float)
    rink_height: Mapped[float] = mapped_column(Float)
    rink_radius: Mapped[float] = mapped_column(Float)


class PriceCategory(Base):
    __tablename__ = "price_categories"
    __table_args__ = ({"schema": "catalog", "info": REFERENCE},)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(7))


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        CheckConstraint("kind IN ('seated', 'standing')", name="kind"),
        {"schema": "catalog", "info": REFERENCE},
    )

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("catalog.venues.id"))
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(Text)  # контур сектора, SVG path
    label_x: Mapped[float] = mapped_column(Float)
    label_y: Mapped[float] = mapped_column(Float)
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    # seated — места с рядом и номером; standing — стоячая зона из безымянных мест.
    kind: Mapped[str] = mapped_column(String(16))
    # Конфигурации зала, в которых сектор продаётся: hockey, stage.
    configs: Mapped[list[str]] = mapped_column(ARRAY(String(16)))


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint("section_id", "row", "number"),
        {"schema": "catalog", "info": REFERENCE},
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("catalog.sections.id"), index=True)
    row: Mapped[str] = mapped_column(String(8))
    number: Mapped[int] = mapped_column(SmallInteger)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    price_category_id: Mapped[int] = mapped_column(ForeignKey("catalog.price_categories.id"))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("kind IN ('concert', 'show', 'sport')", name="kind"),
        CheckConstraint("status IN ('draft', 'published', 'cancelled')", name="status"),
        CheckConstraint("sales_start_at < sales_end_at", name="sales_window"),
        CheckConstraint("sales_end_at <= starts_at", name="sales_before_start"),
        # Афиша: опубликованные мероприятия по дате начала.
        Index("ix_events_status_starts_at", "status", "starts_at"),
        {"schema": "catalog"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, server_default="")
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default=EventStatus.DRAFT.value)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sales_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sales_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    poster_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    prices: Mapped[list["EventPrice"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="EventPrice.price_category_id",
    )


class EventPrice(Base):
    __tablename__ = "event_prices"
    __table_args__ = (
        CheckConstraint("price_kopecks > 0", name="positive"),
        {"schema": "catalog"},
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog.events.id", ondelete="CASCADE"), primary_key=True
    )
    price_category_id: Mapped[int] = mapped_column(
        ForeignKey("catalog.price_categories.id"), primary_key=True
    )
    # Деньги — целые копейки: никаких ошибок округления float.
    price_kopecks: Mapped[int] = mapped_column(Integer)

    event: Mapped[Event] = relationship(back_populates="prices")
