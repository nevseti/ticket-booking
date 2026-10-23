"""Справочные данные площадки (схема зала, категории), закэшированные в памяти процесса.

Схема единственной площадки не меняется во время работы системы, поэтому читается из БД
один раз на процесс. При старте продаж тысячи пользователей открывают схему одновременно —
до PostgreSQL эти запросы не доходят. Сериализованный JSON и ETag тоже считаются один раз.
"""

import asyncio
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.catalog.repository import VenueRepository
from app.modules.catalog.schemas import (
    CategoryOut,
    HallConfigOut,
    RinkOut,
    SeatOut,
    SectionOut,
    VenueLayout,
)
from app.modules.catalog.venue_layout import HallConfig, SectionKind

HALL_CONFIG_NAMES = {
    HallConfig.HOCKEY: "Хоккей: трибуны вокруг льда",
    HallConfig.STAGE: "Сцена: подкова трибун, фан-зона и танцпол",
}


class VenueNotSeededError(AppError):
    status_code = 503
    code = "VENUE_NOT_SEEDED"
    title = "Схема площадки не загружена: выполните seed-venue"


@dataclass(frozen=True)
class SeatRef:
    id: int
    section_id: int
    section_code: str
    section_name: str
    section_kind: SectionKind
    configs: frozenset[HallConfig]  # режимы зала, в которых место продаётся
    row: str
    number: int
    category_id: int


@dataclass(frozen=True)
class ReferenceData:
    layout: VenueLayout
    layout_json: bytes
    etag: str
    categories: dict[int, CategoryOut]
    config_categories: dict[HallConfig, frozenset[int]]
    seats: dict[int, SeatRef]


_cache: ReferenceData | None = None
_lock = asyncio.Lock()


async def _load(session: AsyncSession) -> ReferenceData:
    repo = VenueRepository(session)
    venue = await repo.get_venue()
    if venue is None:
        raise VenueNotSeededError()
    categories = [CategoryOut(id=c.id, name=c.name, color=c.color) for c in await repo.categories()]
    sections = await repo.sections()
    seats = await repo.seats()

    by_section = {s.id: s for s in sections}
    capacity = Counter(seat.section_id for seat in seats)
    section_category = {seat.section_id: seat.price_category_id for seat in seats}

    config_categories: dict[HallConfig, set[int]] = defaultdict(set)
    config_capacity: Counter[HallConfig] = Counter()
    for seat in seats:
        for config in by_section[seat.section_id].configs:
            config_categories[HallConfig(config)].add(seat.price_category_id)
            config_capacity[HallConfig(config)] += 1

    layout = VenueLayout(
        name=venue.name,
        address=venue.address,
        width=venue.width,
        height=venue.height,
        rink=RinkOut(
            x=venue.rink_x,
            y=venue.rink_y,
            width=venue.rink_width,
            height=venue.rink_height,
            radius=venue.rink_radius,
        ),
        stage_path=venue.stage_path,
        categories=categories,
        hall_configs=[
            HallConfigOut(
                id=config,
                name=HALL_CONFIG_NAMES[config],
                capacity=config_capacity[config],
                category_ids=sorted(config_categories[config]),
            )
            for config in HallConfig
        ],
        sections=[
            SectionOut(
                id=s.id,
                code=s.code,
                name=s.name,
                path=s.path,
                label_x=s.label_x,
                label_y=s.label_y,
                kind=s.kind,
                configs=s.configs,
                capacity=capacity[s.id],
                category_id=section_category.get(s.id) if s.kind == SectionKind.STANDING else None,
            )
            for s in sections
        ],
        # Места стоячих зон безымянные: на схеме зона рисуется целиком, без кружков.
        seats=[
            SeatOut(
                id=s.id,
                section_id=s.section_id,
                row=s.row,
                number=s.number,
                x=s.x,
                y=s.y,
                category_id=s.price_category_id,
            )
            for s in seats
            if by_section[s.section_id].kind == SectionKind.SEATED
        ],
    )
    layout_json = layout.model_dump_json().encode()
    return ReferenceData(
        layout=layout,
        layout_json=layout_json,
        etag=f'"{hashlib.sha256(layout_json).hexdigest()[:32]}"',
        categories={c.id: c for c in categories},
        config_categories={k: frozenset(v) for k, v in config_categories.items()},
        seats={
            s.id: SeatRef(
                id=s.id,
                section_id=s.section_id,
                section_code=by_section[s.section_id].code,
                section_name=by_section[s.section_id].name,
                section_kind=SectionKind(by_section[s.section_id].kind),
                configs=frozenset(HallConfig(c) for c in by_section[s.section_id].configs),
                row=s.row,
                number=s.number,
                category_id=s.price_category_id,
            )
            for s in seats
        },
    )


async def get_reference(session: AsyncSession) -> ReferenceData:
    global _cache
    if _cache is not None:
        return _cache
    async with _lock:  # один запрос в БД, даже если пришли сотни запросов одновременно
        if _cache is None:
            _cache = await _load(session)
    return _cache


def reset_reference_cache() -> None:
    """Сбросить кэш (после пересева площадки и в тестах)."""
    global _cache
    _cache = None
