"""Справочные данные площадки (схема зала, категории), закэшированные в памяти процесса.

Схема единственной площадки не меняется во время работы системы, поэтому читается из БД
один раз на процесс. При старте продаж тысячи пользователей открывают схему одновременно —
до PostgreSQL эти запросы не доходят. Сериализованный JSON и ETag тоже считаются один раз.
"""

import asyncio
import hashlib
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.catalog.repository import VenueRepository
from app.modules.catalog.schemas import CategoryOut, SeatOut, SectionOut, VenueLayout


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
    row: str
    number: int
    category_id: int


@dataclass(frozen=True)
class ReferenceData:
    layout: VenueLayout
    layout_json: bytes
    etag: str
    categories: dict[int, CategoryOut]
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

    layout = VenueLayout(
        name=venue.name,
        address=venue.address,
        width=venue.width,
        height=venue.height,
        stage_path=venue.stage_path,
        categories=categories,
        sections=[
            SectionOut(
                id=s.id, code=s.code, name=s.name, path=s.path, label_x=s.label_x, label_y=s.label_y
            )
            for s in sections
        ],
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
        ],
    )
    layout_json = layout.model_dump_json().encode()
    by_section = {s.id: s for s in sections}
    return ReferenceData(
        layout=layout,
        layout_json=layout_json,
        etag=f'"{hashlib.sha256(layout_json).hexdigest()[:32]}"',
        categories={c.id: c for c in categories},
        seats={
            s.id: SeatRef(
                id=s.id,
                section_id=s.section_id,
                section_code=by_section[s.section_id].code,
                section_name=by_section[s.section_id].name,
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
