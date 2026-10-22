"""Засев справочных данных площадки и демонстрационных мероприятий."""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class DemoEvent:
    title: str
    kind: EventKind
    in_days: int  # через сколько дней мероприятие
    hour: int  # время начала по Москве
    prices: tuple[int, int, int, int]  # ₽: VIP, партер, амфитеатр, балкон
    description: str
    sales_in_days: int = 0  # 0 — продажи уже открыты; N — откроются через N дней в 12:00


# Учебные данные: концерты вымышленные, билеты ненастоящие (оплата — имитация).
DEMO_EVENTS = [
    DemoEvent(
        "Big Baby Tape. Dragonborn Arena Show",
        EventKind.CONCERT,
        16,
        20,
        (9900, 6500, 4200, 2800),
        "Большое шоу с новым светом и пиротехникой: хиты от «Gimme The Loot» до свежих треков. "
        "Танцпартер перед сценой — для тех, кто пришёл качать.",
    ),
    DemoEvent(
        "OG Buda. Опасный сольник",
        EventKind.CONCERT,
        23,
        20,
        (8500, 5500, 3500, 2300),
        "Мелодичный трэп и любимые фиты в одном сете. Специальные гости — сюрприз до последнего.",
    ),
    DemoEvent(
        "Дора. Большой сольный концерт",
        EventKind.CONCERT,
        30,
        19,
        (7000, 4800, 3200, 2000),
        "Кьют-рок, гитары и песни, которые зал знает наизусть. Берите друзей — будет громко.",
    ),
    DemoEvent(
        "Скриптонит. Праздник на улице",
        EventKind.CONCERT,
        41,
        20,
        (11000, 7500, 4900, 3200),
        "Живой состав, джаз-вставки и долгожданные треки. Продажи откроются через три дня — "
        "успейте в момент старта.",
        sales_in_days=3,
    ),
    DemoEvent(
        "MAYOT. Арена-тур",
        EventKind.CONCERT,
        12,
        20,
        (7500, 5000, 3300, 2100),
        "Первый большой сольник на арене: все хиты и премьера новых песен.",
    ),
    DemoEvent(
        "Платина. Ночной сет",
        EventKind.CONCERT,
        19,
        21,
        (6900, 4500, 3000, 1900),
        "Атмосферный вечер с визуальным шоу на весь зал.",
    ),
    DemoEvent(
        "Мукка. Акустика и электричество",
        EventKind.CONCERT,
        34,
        19,
        (6000, 4200, 2800, 1700),
        "Первая половина — акустический сет, вторая — громкий электрический.",
    ),
    DemoEvent(
        "INSTASAMKA. Шоу",
        EventKind.CONCERT,
        27,
        20,
        (9500, 6200, 3900, 2500),
        "Танцы, костюмы и хореография — шоу, которое снимают на телефоны с первого трека.",
    ),
    DemoEvent(
        "Кишлак. Большой концерт",
        EventKind.CONCERT,
        48,
        20,
        (6500, 4500, 3000, 1800),
        "Пост-панк, драйв и слэм в партере. Для своих.",
    ),
    DemoEvent(
        "Макс Корж. Зимний стадионный вечер",
        EventKind.CONCERT,
        62,
        19,
        (12000, 8000, 5000, 3500),
        "Песни, под которые поёт весь зал. Продажи стартуют через неделю.",
        sales_in_days=7,
    ),
    DemoEvent(
        "Хоккей. Финал регулярного чемпионата",
        EventKind.SPORT,
        9,
        19,
        (9000, 5000, 3000, 1800),
        "Решающий матч сезона: лидеры конференции в борьбе за первое место.",
    ),
    DemoEvent(
        "Большой стендап-концерт",
        EventKind.SHOW,
        6,
        20,
        (5000, 3500, 2200, 1200),
        "Пять комиков, два часа без перерыва. 18+.",
    ),
]


async def seed_demo_events(session: AsyncSession, now: datetime) -> int:
    """Опубликованные демо-мероприятия. Только если мероприятий ещё нет."""
    if await session.scalar(select(Event.id).limit(1)) is not None:
        return 0
    today = now.astimezone(MSK)
    for demo in DEMO_EVENTS:
        starts_at = _at(today + timedelta(days=demo.in_days), demo.hour)
        sales_start = (
            now - timedelta(days=1)
            if demo.sales_in_days == 0
            else _at(today + timedelta(days=demo.sales_in_days), 12)
        )
        session.add(
            Event(
                title=demo.title,
                description=demo.description,
                kind=demo.kind,
                status=EventStatus.PUBLISHED,
                starts_at=starts_at,
                sales_start_at=sales_start,
                sales_end_at=starts_at,
                published_at=now,
                prices=[
                    EventPrice(price_category_id=category, price_kopecks=rubles * 100)
                    for category, rubles in enumerate(demo.prices, start=1)
                ],
            )
        )
    await session.flush()
    return len(DEMO_EVENTS)
