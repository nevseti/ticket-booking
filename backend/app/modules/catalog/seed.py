"""Засев справочных данных площадки и демонстрационных мероприятий."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import (
    Event,
    EventKind,
    EventPrice,
    EventStatus,
    PriceCategory,
    Seat,
    Section,
    Venue,
)
from app.modules.catalog.venue_layout import build_arena

MSK = ZoneInfo("Europe/Moscow")


async def seed_venue(session: AsyncSession) -> int:
    """Создать площадку со схемой зала. Идемпотентно: если площадка есть — ничего не делает.

    Возвращает число созданных мест (0, если площадка уже была).
    """
    if await session.scalar(select(Venue.id).limit(1)) is not None:
        return 0

    spec = build_arena()
    await session.execute(
        insert(PriceCategory),
        [{"id": c.id, "name": c.name, "color": c.color} for c in spec.categories],
    )
    venue = Venue(
        name=spec.name,
        address=spec.address,
        width=spec.width,
        height=spec.height,
        stage_path=spec.stage_path,
    )
    session.add(venue)
    await session.flush()

    seat_rows = []
    for order, section_spec in enumerate(spec.sections, start=1):
        section = Section(
            venue_id=venue.id,
            code=section_spec.code,
            name=section_spec.name,
            path=section_spec.path,
            label_x=section_spec.label_x,
            label_y=section_spec.label_y,
            sort_order=order,
        )
        session.add(section)
        await session.flush()
        seat_rows += [
            {
                "section_id": section.id,
                "row": s.row,
                "number": s.number,
                "x": s.x,
                "y": s.y,
                "price_category_id": s.category_id,
            }
            for s in section_spec.seats
        ]
    await session.execute(insert(Seat), seat_rows)
    return len(seat_rows)


def _at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day.date(), time(hour, minute), tzinfo=MSK)


# (название, вид, через сколько дней, час начала, продажи открываются через N дней,
#  цены по категориям 1..4 в рублях, описание)
DEMO_EVENTS = [
    (
        "Симфонический оркестр: Шостакович, Симфония № 7",
        EventKind.CONCERT,
        9,
        19,
        0,
        (7500, 4500, 2800, 1500),
        "Ленинградская симфония в исполнении Большого симфонического оркестра.",
    ),
    (
        "Хоккей. Финал регулярного чемпионата",
        EventKind.SPORT,
        14,
        19,
        0,
        (9000, 5000, 3000, 1800),
        "Решающий матч сезона: лидеры конференции в борьбе за первое место.",
    ),
    (
        "Балет «Щелкунчик»",
        EventKind.THEATRE,
        30,
        18,
        2,
        (12000, 8000, 4500, 2500),
        "Новогодняя сказка Чайковского. Продажи открываются через два дня.",
    ),
    (
        "Большой стендап-концерт",
        EventKind.SHOW,
        6,
        20,
        0,
        (5000, 3500, 2200, 1200),
        "Пять комиков, два часа без перерыва. 18+.",
    ),
    (
        "Рок-фестиваль «Северное сияние»",
        EventKind.CONCERT,
        45,
        17,
        0,
        (8500, 6000, 3500, 2000),
        "Шесть групп на одной сцене, финал — с пиротехническим шоу.",
    ),
    (
        "Баскетбол. Матч всех звёзд",
        EventKind.SPORT,
        21,
        16,
        0,
        (6000, 4000, 2500, 1400),
        "Конкурс трёхочковых, слэм-данк контест и матч звёзд лиги.",
    ),
]


async def seed_demo_events(session: AsyncSession, now: datetime) -> int:
    """Опубликованные демо-мероприятия. Только если мероприятий ещё нет."""
    if await session.scalar(select(Event.id).limit(1)) is not None:
        return 0
    today = now.astimezone(MSK)
    for title, kind, days, hour, sales_in_days, prices, description in DEMO_EVENTS:
        starts_at = _at(today + timedelta(days=days), hour)
        sales_start = (
            now - timedelta(days=1)
            if sales_in_days == 0
            else _at(today + timedelta(days=sales_in_days), 12)
        )
        session.add(
            Event(
                title=title,
                description=description,
                kind=kind,
                status=EventStatus.PUBLISHED,
                starts_at=starts_at,
                sales_start_at=sales_start,
                sales_end_at=starts_at,
                published_at=now,
                prices=[
                    EventPrice(price_category_id=category, price_kopecks=rubles * 100)
                    for category, rubles in enumerate(prices, start=1)
                ],
            )
        )
    await session.flush()
    return len(DEMO_EVENTS)
