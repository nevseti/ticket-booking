"""Засев справочных данных площадки и демонстрационных мероприятий."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import delete, insert, select, text, update
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
from app.modules.catalog.reference import reset_reference_cache
from app.modules.catalog.venue_layout import LAYOUT_VERSION, LOUNGE, VIP, VenueSpec, build_arena

MSK = ZoneInfo("Europe/Moscow")

log = structlog.get_logger()


async def seed_venue(session: AsyncSession) -> int:
    """Создать площадку со схемой зала или перестроить устаревшую. Идемпотентно.

    Ценовые категории обновляются всегда (upsert): их названия и цвета берутся из кода.
    Возвращает число созданных мест (0 — площадка уже актуальна).
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
    venue = await session.scalar(select(Venue).limit(1))
    if venue is None:
        venue = Venue()
        _apply_geometry(venue, spec)
        session.add(venue)
        await session.flush()
        return await _insert_layout(session, venue.id, spec)
    if venue.layout_version >= LAYOUT_VERSION:
        return 0
    created = await _relayout(session, venue, spec)
    reset_reference_cache()  # id мест изменились — кэш справочника этого процесса устарел
    return created


def _apply_geometry(venue: Venue, spec: VenueSpec) -> None:
    venue.name = spec.name
    venue.address = spec.address
    venue.width = spec.width
    venue.height = spec.height
    venue.stage_path = spec.stage_path
    venue.rink_x = spec.rink.x
    venue.rink_y = spec.rink.y
    venue.rink_width = spec.rink.width
    venue.rink_height = spec.rink.height
    venue.rink_radius = spec.rink.radius
    venue.boxes = [{"x": b.x, "y": b.y, "width": b.width, "height": b.height} for b in spec.boxes]
    venue.layout_version = LAYOUT_VERSION


async def _insert_layout(session: AsyncSession, venue_id: int, spec: VenueSpec) -> int:
    seat_rows = []
    for order, section_spec in enumerate(spec.sections, start=1):
        section = Section(
            venue_id=venue_id,
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


# Сначала собираем соответствие «старое место → новое» по адресу (сектор, ряд, номер).
_SEAT_KEYS_SQL = text("""
    SELECT s.id, sec.code, s.row, s.number
    FROM catalog.seats s JOIN catalog.sections sec ON sec.id = s.section_id
""")


async def _relayout(session: AsyncSession, venue: Venue, spec: VenueSpec) -> int:
    """Перестроить схему зала, сохранив уже проданное.

    Это служебная операция того же рода, что миграция БД, поэтому она работает с таблицами
    бронирования и заказов напрямую, мимо фасадов модулей. Места получают НОВЫЕ id
    (последовательность не сбрасывается), и проданные места, удержания и билеты переносятся
    на места с тем же адресом «сектор, ряд, номер». Если такого места в новой схеме нет:
    проданное место снимается, удержание гасится, а билет остаётся как есть — в нём
    сохранены сектор, ряд и номер текстом.
    """
    old = {row.id: (row.code, row.row, row.number) for row in await session.execute(_SEAT_KEYS_SQL)}
    await session.execute(delete(Seat))
    await session.execute(delete(Section).where(Section.venue_id == venue.id))
    _apply_geometry(venue, spec)
    created = await _insert_layout(session, venue.id, spec)
    new = {(row.code, row.row, row.number): row.id for row in await session.execute(_SEAT_KEYS_SQL)}
    mapping = [(old_id, new[key]) for old_id, key in old.items() if key in new]

    await session.execute(
        text("CREATE TEMP TABLE seat_map (old_id int PRIMARY KEY, new_id int) ON COMMIT DROP")
    )
    if mapping:
        await session.execute(
            text("INSERT INTO seat_map SELECT * FROM unnest(CAST(:o AS int[]), CAST(:n AS int[]))"),
            {"o": [m[0] for m in mapping], "n": [m[1] for m in mapping]},
        )
    moved = {}
    for table in ("booking.sold_seats", "booking.holds", "orders.tickets"):
        result = await session.execute(
            text(
                f"UPDATE {table} t SET seat_id = m.new_id "
                "FROM seat_map m WHERE t.seat_id = m.old_id"
            )
        )
        moved[table] = result.rowcount
    lost_sold = await session.execute(
        text("DELETE FROM booking.sold_seats WHERE seat_id NOT IN (SELECT id FROM catalog.seats)")
    )
    lost_holds = await session.execute(
        text("""
            UPDATE booking.holds SET status = 'expired', closed_at = now()
            WHERE status = 'active' AND seat_id NOT IN (SELECT id FROM catalog.seats)
        """)
    )
    await _ensure_category_prices(session)
    log.info(
        "venue_relayout",
        layout_version=LAYOUT_VERSION,
        seats=created,
        moved=moved,
        sold_removed=lost_sold.rowcount,
        holds_expired=lost_holds.rowcount,
    )
    return created


# Новая категория (лаунж) появилась после того, как мероприятия уже созданы: её цена —
# 75 % от VIP, округлённо до 100 ₽. Без цены места категории не продаются (EventInfo.sells).
NEW_CATEGORY_PRICES = {LOUNGE: (VIP, 0.75)}


async def _ensure_category_prices(session: AsyncSession) -> None:
    for category, (base, share) in NEW_CATEGORY_PRICES.items():
        await session.execute(
            text("""
                INSERT INTO catalog.event_prices (event_id, price_category_id, price_kopecks)
                SELECT p.event_id, :category, GREATEST(
                    CAST(round(p.price_kopecks * CAST(:share AS numeric) / 10000) * 10000 AS int),
                    10000
                )
                FROM catalog.event_prices p
                WHERE p.price_category_id = :base
                  AND NOT EXISTS (
                      SELECT 1 FROM catalog.event_prices x
                      WHERE x.event_id = p.event_id AND x.price_category_id = :category
                  )
            """),
            {"category": category, "base": base, "share": share},
        )


# --- Демо-афиша --------------------------------------------------------------------------


def _at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day.date(), time(hour, minute), tzinfo=MSK)


def _lounge(vip: int) -> int:
    """Лаунж на торцах — 75 % от VIP на длинных сторонах, округлённо до 100 ₽."""
    return round(vip * 0.75 / 100) * 100


def stage_prices(
    vip: int, fan: int, dance: int, lower: int, middle: int, upper: int
) -> dict[int, int]:
    """Цены концерта/шоу в рублях: VIP, фан-зона, танцпол, нижний/средний/верхний ярус
    (лаунж считается от VIP)."""
    return {1: vip, 2: fan, 3: dance, 4: lower, 5: middle, 6: upper, 7: _lounge(vip)}


def hockey_prices(vip: int, lower: int, middle: int, upper: int) -> dict[int, int]:
    """Цены хоккея в рублях: VIP, нижний/средний/верхний ярус (партера на льду нет),
    лаунж считается от VIP."""
    return {1: vip, 4: lower, 5: middle, 6: upper, 7: _lounge(vip)}


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
        "Noize MC. Живой звук",
        EventKind.CONCERT,
        41,
        20,
        stage_prices(17000, 11000, 7500, 8500, 5500, 3300),
        "Живой состав, гитары и долгожданные треки. Продажи откроются через три "
        "дня — успейте в момент старта.",
        sales_in_days=3,
    ),
    DemoEvent(
        "Элджей. Арена-тур",
        EventKind.CONCERT,
        12,
        20,
        stage_prices(11500, 7500, 5000, 5800, 3900, 2300),
        "Первый большой сольник на арене: все хиты и премьера новых песен.",
    ),
    DemoEvent(
        "Cream Soda. Ночной сет",
        EventKind.CONCERT,
        19,
        21,
        stage_prices(10500, 6900, 4500, 5200, 3500, 2100),
        "Танцевальная электроника и визуальное шоу на весь зал до глубокой ночи.",
    ),
    DemoEvent(
        "Три дня дождя. Акустика и электричество",
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


# Фото артистов со свободными лицензиями с Wikimedia Commons (скачаны, ужаты в WebP и лежат
# в frontend/public/posters). Лицензии CC BY / CC BY-SA требуют указать автора — подпись
# выводится на странице мероприятия. У хоккея и шоу фото нет: их обложки рисует фронтенд
# (эмблемы команд, иллюстрации шоу).
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
        "Фото: MONO, CC BY 3.0, Wikimedia Commons (кадр из видео, тонирование)",
        "https://commons.wikimedia.org/wiki/File:%D0%94%D0%BE%D1%80%D0%B0_-_%D0%B1%D0%BE%D0%BB%D1%8C%D1%88%D0%B5_-_TH%C4%92_MONO_SHOW.webm",
    ),
    "Noize MC. Живой звук": (
        "/posters/noize-mc.webp",
        "Фото: Kerrin Key, CC BY-SA 2.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Noize_MC_2020_(2).jpg",
    ),
    "Элджей. Арена-тур": (
        "/posters/eldzhey.webp",
        "Фото: Okras, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:%D0%AD%D0%BB%D0%B4%D0%B6%D0%B5%D0%B9_(3)_%D0%BD%D0%B0_Big_Love_Show_2018_%D0%B2_%D0%A1%D0%9F%D0%B1.jpg",
    ),
    "Cream Soda. Ночной сет": (
        "/posters/cream-soda.webp",
        "Фото: Heyitsvad, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Cream_Soda,_2022.jpg",
    ),
    "Три дня дождя. Акустика и электричество": (
        "/posters/tri-dnya-dozhdya.webp",
        "Фото: Okras, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:%D0%A2%D1%80%D0%B8_%D0%B4%D0%BD%D1%8F_%D0%B4%D0%BE%D0%B6%D0%B4%D1%8F_%D0%BD%D0%B0_VK_Fest_2025_%D0%B2_%D0%A1%D0%9F%D0%B1_(cropped).jpg",
    ),
    "INSTASAMKA. Шоу": (
        "/posters/instasamka.webp",
        "Фото: Передача До 17 и старше, CC BY 3.0, Wikimedia Commons (кадрирование)",
        "https://commons.wikimedia.org/wiki/File:Instasamka_performs_%22Za_dengi_da%22_(Jun_2024;_2).png",
    ),
    "Кишлак. Большой концерт": (
        "/posters/kishlak.webp",
        "Фото: JessePinkman, CC BY 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:%D0%9A%D0%B8%D1%88%D0%BB%D0%B0%D0%BA_2024.jpg",
    ),
    "Макс Корж. Зимний вечер на арене": (
        "/posters/max-korzh.webp",
        "Фото: Itokyl, CC BY-SA 4.0, Wikimedia Commons",
        "https://commons.wikimedia.org/wiki/File:Max-Korzh-2018-11-09-0003.jpg",
    ),
}


def _demo_dates(demo: DemoEvent, now: datetime) -> tuple[datetime, datetime]:
    """Начало мероприятия и старт продаж — относительно «сегодня»."""
    today = now.astimezone(MSK)
    starts_at = _at(today + timedelta(days=demo.in_days), demo.hour)
    sales_start = (
        now - timedelta(days=1)
        if demo.sales_in_days == 0
        else _at(today + timedelta(days=demo.sales_in_days), 12)
    )
    return starts_at, sales_start


async def refresh_demo_dates(session: AsyncSession, now: datetime) -> int:
    """Сдвинуть даты демо-мероприятий от сегодняшнего дня, как при засеве.

    Нужно перед показом: даты считались от дня засева и со временем уходят в прошлое.
    В отличие от seed-demo --reset ничего не удаляет — заказы и билеты остаются.
    """
    updated = 0
    for demo in DEMO_EVENTS:
        starts_at, sales_start = _demo_dates(demo, now)
        result = await session.execute(
            update(Event)
            .where(Event.title == demo.title, Event.status != EventStatus.CANCELLED)
            .values(starts_at=starts_at, sales_start_at=sales_start, sales_end_at=starts_at)
        )
        updated += result.rowcount or 0
    return updated


async def seed_demo_events(session: AsyncSession, now: datetime, *, reset: bool = False) -> int:
    """Опубликованные демо-мероприятия. Без reset — только если мероприятий ещё нет."""
    if reset:
        await session.execute(delete(Event))
    elif await session.scalar(select(Event.id).limit(1)) is not None:
        return 0
    for demo in DEMO_EVENTS:
        starts_at, sales_start = _demo_dates(demo, now)
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


# Демо-концерты, заменённые на артистов, у которых есть свободные фото: старое название → новое.
# apply-posters переименовывает их на месте, не трогая уже купленные билеты.
DEMO_RENAMES = {
    "Скриптонит. Праздник на улице": "Noize MC. Живой звук",
    "MAYOT. Арена-тур": "Элджей. Арена-тур",
    "Платина. Ночной сет": "Cream Soda. Ночной сет",
    "Мукка. Акустика и электричество": "Три дня дождя. Акустика и электричество",
}


async def apply_demo_posters(session: AsyncSession) -> int:
    """Проставить фото демо-мероприятиям по названию (без пересоздания мероприятий).

    Демо-мероприятиям без фото в DEMO_POSTERS обложка сбрасывается — их рисует фронтенд.
    """
    descriptions = {demo.title: demo.description for demo in DEMO_EVENTS}
    for old, new in DEMO_RENAMES.items():
        await session.execute(
            update(Event).where(Event.title == old).values(title=new, description=descriptions[new])
        )
    updated = 0
    for demo in DEMO_EVENTS:
        url, credit, source = DEMO_POSTERS.get(demo.title, (None, None, None))
        result = await session.execute(
            update(Event)
            .where(Event.title == demo.title)
            .values(poster_url=url, poster_credit=credit, poster_source=source)
        )
        updated += result.rowcount or 0
    return updated
