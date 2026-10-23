"""Засев справочных данных площадки и демонстрационных мероприятий."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

    Ценовые категории обновляются всегда (upsert): их названия и цвета берутся из кода.
    Возвращает число созданных мест (0, если площадка уже была).
    """
    spec = build_arena()
    upsert = pg_insert(PriceCategory).values(
        [{"id": c.id, "name": c.name, "color": c.color} for c in spec.categories]
    )
    await session.execute(
        upsert.on_conflict_do_update(
            index_elements=[PriceCategory.id],
            set_={"name": upsert.excluded.name, "color": upsert.excluded.color},
        )
    )
    if await session.scalar(select(Venue.id).limit(1)) is not None:
        return 0

    venue = Venue(
        name=spec.name,
        address=spec.address,
        width=spec.width,
        height=spec.height,
        stage_path=spec.stage_path,
        rink_x=spec.rink.x,
        rink_y=spec.rink.y,
        rink_width=spec.rink.width,
        rink_height=spec.rink.height,
        rink_radius=spec.rink.radius,
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
            kind=section_spec.kind,
            configs=list(section_spec.configs),
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


# --- Демо-афиша --------------------------------------------------------------------------


def _at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day.date(), time(hour, minute), tzinfo=MSK)


def stage_prices(
    vip: int, fan: int, dance: int, lower: int, middle: int, upper: int
) -> dict[int, int]:
    """Цены концерта/шоу в рублях: VIP, фан-зона, танцпол, нижний/средний/верхний ярус."""
    return {1: vip, 2: fan, 3: dance, 4: lower, 5: middle, 6: upper}


def hockey_prices(vip: int, lower: int, middle: int, upper: int) -> dict[int, int]:
    """Цены хоккея в рублях: VIP, нижний/средний/верхний ярус (партера на льду нет)."""
    return {1: vip, 4: lower, 5: middle, 6: upper}


@dataclass(frozen=True)
class DemoEvent:
    title: str
    kind: EventKind
    in_days: int  # через сколько дней мероприятие
    hour: int  # время начала по Москве
    prices: dict[int, int]  # id категории → цена в рублях
    description: str
    sales_in_days: int = 0  # 0 — продажи уже открыты; N — откроются через N дней в 12:00


# Учебные данные: мероприятия вымышленные, билеты ненастоящие (оплата — имитация).
DEMO_EVENTS = [
    # --- Концерты ---
    DemoEvent(
        "Big Baby Tape. Dragonborn Arena Show",
        EventKind.CONCERT,
        16,
        20,
        stage_prices(15000, 9900, 6500, 7500, 4900, 2900),
        "Большое шоу с новым светом и пиротехникой: хиты от «Gimme The Loot» до свежих "
        "треков. Фан-зона у сцены — для тех, кто пришёл качать.",
    ),
    DemoEvent(
        "OG Buda. Опасный сольник",
        EventKind.CONCERT,
        23,
        20,
        stage_prices(13000, 8500, 5500, 6500, 4200, 2500),
        "Мелодичный трэп и любимые фиты в одном сете. Специальные гости — сюрприз до последнего.",
    ),
    DemoEvent(
        "Дора. Большой сольный концерт",
        EventKind.CONCERT,
        30,
        19,
        stage_prices(11000, 7000, 4800, 5500, 3800, 2200),
        "Кьют-рок, гитары и песни, которые зал знает наизусть. Берите друзей — будет громко.",
    ),
    DemoEvent(
        "Скриптонит. Праздник на улице",
        EventKind.CONCERT,
        41,
        20,
        stage_prices(17000, 11000, 7500, 8500, 5500, 3300),
        "Живой состав, джаз-вставки и долгожданные треки. Продажи откроются через три "
        "дня — успейте в момент старта.",
        sales_in_days=3,
    ),
    DemoEvent(
        "MAYOT. Арена-тур",
        EventKind.CONCERT,
        12,
        20,
        stage_prices(11500, 7500, 5000, 5800, 3900, 2300),
        "Первый большой сольник на арене: все хиты и премьера новых песен.",
    ),
    DemoEvent(
        "Платина. Ночной сет",
        EventKind.CONCERT,
        19,
        21,
        stage_prices(10500, 6900, 4500, 5200, 3500, 2100),
        "Атмосферный вечер с визуальным шоу на весь зал.",
    ),
    DemoEvent(
        "Мукка. Акустика и электричество",
        EventKind.CONCERT,
        34,
        19,
        stage_prices(9000, 6000, 4200, 4800, 3200, 1900),
        "Первая половина — акустический сет, вторая — громкий электрический.",
    ),
    DemoEvent(
        "INSTASAMKA. Шоу",
        EventKind.CONCERT,
        27,
        20,
        stage_prices(14500, 9500, 6200, 7200, 4600, 2700),
        "Танцы, костюмы и хореография — шоу, которое снимают на телефоны с первого трека.",
    ),
    DemoEvent(
        "Кишлак. Большой концерт",
        EventKind.CONCERT,
        48,
        20,
        stage_prices(9500, 6500, 4500, 5000, 3300, 2000),
        "Пост-панк, драйв и слэм на танцполе. Для своих.",
    ),
    DemoEvent(
        "Макс Корж. Зимний вечер на арене",
        EventKind.CONCERT,
        62,
        19,
        stage_prices(18000, 12000, 8000, 9000, 6000, 3800),
        "Песни, под которые поёт весь зал. Продажи стартуют через неделю.",
        sales_in_days=7,
    ),
    # --- Шоу ---
    DemoEvent(
        "Ледовое шоу «Щелкунчик»",
        EventKind.SHOW,
        45,
        18,
        stage_prices(9000, 6000, 4500, 5000, 3500, 2000),
        "Новогодняя история на льду: чемпионы мира по фигурному катанию, живой оркестр "
        "и световые проекции. Для всей семьи.",
    ),
    DemoEvent(
        "Импровизация. Большой тур",
        EventKind.SHOW,
        14,
        19,
        stage_prices(8000, 5500, 4000, 4500, 3000, 1800),
        "Четыре импровизатора, ни одной заготовки: каждая сцена рождается из ваших подсказок. 16+.",
    ),
    DemoEvent(
        "Большой стендап-концерт",
        EventKind.SHOW,
        6,
        20,
        stage_prices(7000, 5000, 3500, 4000, 2600, 1500),
        "Пять комиков, два часа без перерыва. 18+.",
    ),
    DemoEvent(
        "Шоу «Битва битбоксеров»",
        EventKind.SHOW,
        37,
        19,
        stage_prices(6000, 4200, 3200, 3500, 2400, 1400),
        "Финал чемпионата по битбоксу: лупстейшены, дуэты и баттлы на вылет.",
    ),
    # --- Спорт (хоккей) ---
    DemoEvent(
        "Хоккей. Динамо — СКА",
        EventKind.SPORT,
        9,
        19,
        hockey_prices(8000, 3500, 2200, 1200),
        "Регулярный чемпионат: принципиальное противостояние Москвы и Петербурга.",
    ),
    DemoEvent(
        "Хоккей. ЦСКА — Спартак",
        EventKind.SPORT,
        18,
        19,
        hockey_prices(9000, 4000, 2500, 1400),
        "Московское дерби — самый горячий матч месяца, аншлаг гарантирован.",
    ),
    DemoEvent(
        "Хоккей. Динамо — Ак Барс",
        EventKind.SPORT,
        25,
        17,
        hockey_prices(7000, 3000, 1900, 1000),
        "Матч лидеров конференций в выходной день — берите детей на трибуны.",
    ),
    DemoEvent(
        "Хоккей. Матч звёзд",
        EventKind.SPORT,
        55,
        16,
        hockey_prices(12000, 5500, 3500, 2000),
        "Мастер-шоу, конкурсы на скорость и точность бросков и звёздный матч. "
        "Продажи откроются через пять дней.",
        sales_in_days=5,
    ),
]


# Фото со свободными лицензиями с Wikimedia Commons (скачаны, ужаты в WebP и лежат в
# frontend/public/posters). Лицензии CC BY / CC BY-SA требуют указать автора — подпись
# выводится на странице мероприятия.
DEMO_POSTERS: dict[str, tuple[str, str, str]] = {
    "Big Baby Tape. Dragonborn Arena Show": (
        "/posters/big-baby-tape.webp",
        "Фото: Okras, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Big_Baby_Tape_%D0%BD%D0%B0_Teen_City_Day_(2023.05.27).jpg",
    ),
    "OG Buda. Опасный сольник": (
        "/posters/og-buda.webp",
        "Фото: Райпон, CC BY 3.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:OG_Buda_(2021).png",
    ),
    "Дора. Большой сольный концерт": (
        "/posters/dora.webp",
        "Фото: MONO, CC BY 3.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Dora_during_the_Moon_Show_in_2020.png",
    ),
    "Скриптонит. Праздник на улице": (
        "/posters/scriptonite.webp",
        "Фото: Live Stage (YouTube channel), A. Pesotsky, CC BY 3.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Scriptonite.jpg",
    ),
    "INSTASAMKA. Шоу": (
        "/posters/instasamka.webp",
        "Фото: Okras, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Instasamka_%D0%BD%D0%B0_VK_Fest_2023_%D0%B2_%D0%A1%D0%9F%D0%B1.jpg",
    ),
    "Макс Корж. Зимний вечер на арене": (
        "/posters/max-korzh.webp",
        "Фото: Itokyl, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Max-Korzh-2018-11-09-0011.jpg",
    ),
    "Хоккей. Динамо — СКА": (
        "/posters/hockey-dynamo-1.webp",
        "Фото: Voltmetro, CC BY-SA 3.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:2019-01-06_-_KHL_Dynamo_Moscow_vs_Dinamo_Riga_-_Photo_32.jpg",
    ),
    "Хоккей. ЦСКА — Спартак": (
        "/posters/hockey-arena.webp",
        "Фото: Voltmetro, CC BY 3.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Dynamo_Stadium_-_Ice_hockey_arena_-_Panorama_during_match.jpg",
    ),
    "Хоккей. Динамо — Ак Барс": (
        "/posters/hockey-dynamo-2.webp",
        "Фото: Voltmetro, CC BY-SA 3.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:2019-01-06_-_KHL_Dynamo_Moscow_vs_Dinamo_Riga_-_Photo_49.jpg",
    ),
    "Хоккей. Матч звёзд": (
        "/posters/hockey-fans.webp",
        "Фото: Elena Wiki Elena, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Ice_hockey_fans_to_enter_VTB_Ice_Palace_(2016_IIHF_WC).jpg",
    ),
    "Ледовое шоу «Щелкунчик»": (
        "/posters/ice-show.webp",
        "Фото: SKas, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Ice_show_City_Lights.jpg",
    ),
    "Большой стендап-концерт": (
        "/posters/standup.webp",
        "Фото: Carlos Delgado, CC BY-SA 3.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Stand-up_comedy_-_Stage.jpg",
    ),
    "Шоу «Битва битбоксеров»": (
        "/posters/beatbox.webp",
        "Фото: Hinorisakamachi, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Beatbox_House_GBB_2018.png",
    ),
}


async def seed_demo_events(session: AsyncSession, now: datetime, *, reset: bool = False) -> int:
    """Опубликованные демо-мероприятия. Без reset — только если мероприятий ещё нет."""
    if reset:
        await session.execute(delete(Event))
    elif await session.scalar(select(Event.id).limit(1)) is not None:
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
                poster_url=DEMO_POSTERS.get(demo.title, (None, None, None))[0],
                poster_credit=DEMO_POSTERS.get(demo.title, (None, None, None))[1],
                poster_source=DEMO_POSTERS.get(demo.title, (None, None, None))[2],
                prices=[
                    EventPrice(price_category_id=category, price_kopecks=rubles * 100)
                    for category, rubles in demo.prices.items()
                ],
            )
        )
    await session.flush()
    return len(DEMO_EVENTS)


async def apply_demo_posters(session: AsyncSession) -> int:
    """Проставить фото демо-мероприятиям по названию (без пересоздания мероприятий)."""
    updated = 0
    for title, (url, credit, source) in DEMO_POSTERS.items():
        result = await session.execute(
            update(Event)
            .where(Event.title == title)
            .values(poster_url=url, poster_credit=credit, poster_source=source)
        )
        updated += result.rowcount or 0
    return updated
