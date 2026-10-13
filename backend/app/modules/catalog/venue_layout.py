"""Генератор схемы единственной площадки — универсальной арены.

Сцена (или игровая площадка) вверху. Зрительские зоны:

    партер     3 прямоугольных блока, 16 рядов — категории «VIP» (ряды 1–5) и «Партер»
    амфитеатр  5 секторов-дуг, 12 рядов       — категория «Амфитеатр»
    балкон     5 секторов-дуг, 9 рядов        — категория «Балкон»

Координаты — в системе SVG (y вниз). Места на дугах заданы в полярных координатах (r, θ)
относительно фокуса сцены: x = CX + r·sin θ, y = CY + r·cos θ; θ = 0 — прямо под сценой.
Генератор детерминирован: одинаковый результат при каждом запуске.
"""

import math
from dataclasses import dataclass, field

CX, CY = 960.0, 70.0  # фокус дуг — центр сцены
WIDTH, HEIGHT = 1920, 1110
SEAT_PITCH = 16.0  # расстояние между центрами соседних мест в ряду, px
SECTION_PAD = 11.0  # отступ контура сектора от крайних мест


@dataclass(frozen=True)
class CategorySpec:
    id: int
    name: str
    color: str


@dataclass(frozen=True)
class SeatSpec:
    row: str
    number: int
    x: float
    y: float
    category_id: int


@dataclass(frozen=True)
class SectionSpec:
    code: str
    name: str
    path: str
    label_x: float
    label_y: float
    seats: list[SeatSpec] = field(default_factory=list)


@dataclass(frozen=True)
class VenueSpec:
    name: str
    address: str
    width: int
    height: int
    stage_path: str
    categories: list[CategorySpec]
    sections: list[SectionSpec]

    @property
    def seat_count(self) -> int:
        return sum(len(s.seats) for s in self.sections)


CATEGORIES = [
    CategorySpec(1, "VIP", "#e8590c"),
    CategorySpec(2, "Партер", "#7048e8"),
    CategorySpec(3, "Амфитеатр", "#1c7ed6"),
    CategorySpec(4, "Балкон", "#0ca678"),
]


def _fmt(value: float) -> str:
    return f"{value:.1f}"


# --- Партер: прямые ряды ---------------------------------------------------------------

PARTERRE_TOP = 220.0
PARTERRE_ROWS = 16
PARTERRE_ROW_STEP = 18.0
PARTERRE_AISLE = 28.0
PARTERRE_BLOCKS = [
    ("P1", "Партер, левый", 13),
    ("P2", "Партер, центр", 18),
    ("P3", "Партер, правый", 13),
]


def _parterre_sections() -> list[SectionSpec]:
    widths = [(seats - 1) * SEAT_PITCH for _, _, seats in PARTERRE_BLOCKS]
    total = sum(widths) + PARTERRE_AISLE * (len(widths) - 1) + 2 * SECTION_PAD * len(widths)
    left = CX - total / 2
    sections = []
    for (code, name, per_row), width in zip(PARTERRE_BLOCKS, widths, strict=True):
        x0 = left + SECTION_PAD
        seats = [
            SeatSpec(
                row=str(row),
                number=number,
                x=round(x0 + (number - 1) * SEAT_PITCH, 1),
                y=round(PARTERRE_TOP + (row - 1) * PARTERRE_ROW_STEP, 1),
                category_id=1 if row <= 5 else 2,
            )
            for row in range(1, PARTERRE_ROWS + 1)
            for number in range(1, per_row + 1)
        ]
        x1, x2 = left, left + width + 2 * SECTION_PAD
        y1 = PARTERRE_TOP - SECTION_PAD
        y2 = PARTERRE_TOP + (PARTERRE_ROWS - 1) * PARTERRE_ROW_STEP + SECTION_PAD
        path = f"M {_fmt(x1)} {_fmt(y1)} H {_fmt(x2)} V {_fmt(y2)} H {_fmt(x1)} Z"
        sections.append(
            SectionSpec(code, name, path, round((x1 + x2) / 2, 1), round(y1 - 14, 1), seats)
        )
        left = x2 + PARTERRE_AISLE
    return sections


# --- Амфитеатр и балкон: дуги вокруг сцены ----------------------------------------------


@dataclass(frozen=True)
class _ArcTier:
    code: str
    name: str
    category_id: int
    first_radius: float
    rows: int
    row_step: float
    half_span_deg: float
    sections: int
    aisle_deg: float


ARC_TIERS = [
    _ArcTier("A", "Амфитеатр", 3, 600, 12, 18, 62, 5, 2.5),
    _ArcTier("B", "Балкон", 4, 840, 9, 19, 66, 5, 2.5),
]


def _point(r: float, theta: float) -> tuple[float, float]:
    return CX + r * math.sin(theta), CY + r * math.cos(theta)


def _sector_path(r_in: float, r_out: float, t1: float, t2: float) -> str:
    """Кольцевой сектор: внутренняя дуга слева направо (через низ), внешняя — обратно."""
    x1, y1 = _point(r_in, t1)
    x2, y2 = _point(r_in, t2)
    x3, y3 = _point(r_out, t2)
    x4, y4 = _point(r_out, t1)
    return (
        f"M {_fmt(x1)} {_fmt(y1)} "
        f"A {_fmt(r_in)} {_fmt(r_in)} 0 0 0 {_fmt(x2)} {_fmt(y2)} "
        f"L {_fmt(x3)} {_fmt(y3)} "
        f"A {_fmt(r_out)} {_fmt(r_out)} 0 0 1 {_fmt(x4)} {_fmt(y4)} Z"
    )


def _arc_section(tier: _ArcTier, index: int, t1: float, t2: float) -> SectionSpec:
    seats: list[SeatSpec] = []
    for row in range(1, tier.rows + 1):
        r = tier.first_radius + (row - 1) * tier.row_step
        count = int(r * (t2 - t1) // SEAT_PITCH)
        step = SEAT_PITCH / r
        start = (t1 + t2) / 2 - (count - 1) * step / 2
        for number in range(1, count + 1):
            x, y = _point(r, start + (number - 1) * step)
            seats.append(SeatSpec(str(row), number, round(x, 1), round(y, 1), tier.category_id))

    last_radius = tier.first_radius + (tier.rows - 1) * tier.row_step
    pad_angle = SECTION_PAD / last_radius
    path = _sector_path(
        tier.first_radius - SECTION_PAD, last_radius + SECTION_PAD, t1 - pad_angle, t2 + pad_angle
    )
    label_x, label_y = _point(last_radius + SECTION_PAD + 16, (t1 + t2) / 2)
    return SectionSpec(
        code=f"{tier.code}{index + 1}",
        name=f"{tier.name} {index + 1}",
        path=path,
        label_x=round(label_x, 1),
        label_y=round(label_y, 1),
        seats=seats,
    )


def _arc_sections(tier: _ArcTier) -> list[SectionSpec]:
    width = (2 * tier.half_span_deg - tier.aisle_deg * (tier.sections - 1)) / tier.sections
    sections = []
    for i in range(tier.sections):
        start_deg = -tier.half_span_deg + i * (width + tier.aisle_deg)
        sections.append(
            _arc_section(tier, i, math.radians(start_deg), math.radians(start_deg + width))
        )
    return sections


def _stage_path() -> str:
    left, right, top, bottom = CX - 200, CX + 200, 24.0, 96.0
    return (
        f"M {_fmt(left + 12)} {_fmt(top)} H {_fmt(right - 12)} "
        f"Q {_fmt(right)} {_fmt(top)} {_fmt(right)} {_fmt(top + 12)} V {_fmt(bottom)} "
        f"Q {_fmt(CX)} {_fmt(bottom + 54)} {_fmt(left)} {_fmt(bottom)} V {_fmt(top + 12)} "
        f"Q {_fmt(left)} {_fmt(top)} {_fmt(left + 12)} {_fmt(top)} Z"
    )


def build_arena() -> VenueSpec:
    sections = _parterre_sections() + [s for tier in ARC_TIERS for s in _arc_sections(tier)]
    return VenueSpec(
        name="Арена «Северная»",
        address="г. Москва, ул. Примерная, 1",
        width=WIDTH,
        height=HEIGHT,
        stage_path=_stage_path(),
        categories=CATEGORIES,
        sections=sections,
    )
