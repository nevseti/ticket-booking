"""Генератор схемы единственной площадки — ледовой арены (по образцу ВТБ Арены).

В центре — ледовая площадка, вокруг — три яруса трибун. Зал работает в двух конфигурациях:

    hockey  хоккей: трибуны кольцом вокруг льда, включая западный торец;
    stage   концерт/шоу: у западного торца сцена, трибуны — «подковой» (длинные стороны
            тянутся до сцены, западный торец закрыт), на льду две стоячие зоны:
            «Фан-зона» у сцены и «Танцпол».

Стоячая зона — это набор безымянных мест (вместимость зоны). Билет в зону занимает любое
свободное место зоны: защита от двойной продажи работает так же, как для сидячих мест,
и не нужен «горячий» счётчик остатка.

Ряды трибун — «смещённые» контуры площадки: прямой участок вдоль борта или дуга на углу.
Координаты — в системе SVG (y вниз). Генератор детерминирован.
"""

import math
from dataclasses import dataclass, field
from enum import StrEnum


class HallConfig(StrEnum):
    HOCKEY = "hockey"
    STAGE = "stage"


class SectionKind(StrEnum):
    SEATED = "seated"
    STANDING = "standing"


BOTH = (HallConfig.HOCKEY, HallConfig.STAGE)
HOCKEY_ONLY = (HallConfig.HOCKEY,)
STAGE_ONLY = (HallConfig.STAGE,)

WIDTH, HEIGHT = 1720, 1340
CX, CY = 860.0, 670.0

# Ледовая площадка: полуширина, полувысота, радиус скругления углов
RINK_A, RINK_B, RINK_R = 330.0, 165.0, 95.0

SEAT_PITCH = 15.0  # расстояние между центрами мест в ряду
ROW_STEP = 16.0  # расстояние между рядами
HALF_AISLE = 9.0  # половина ширины прохода между секторами
PAD = 8.0  # отступ контура сектора от крайних мест


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
    configs: tuple[HallConfig, ...]
    kind: SectionKind = SectionKind.SEATED
    seats: list[SeatSpec] = field(default_factory=list)


@dataclass(frozen=True)
class RinkSpec:
    x: float
    y: float
    width: float
    height: float
    radius: float


@dataclass(frozen=True)
class VenueSpec:
    name: str
    address: str
    width: int
    height: int
    rink: RinkSpec
    stage_path: str
    categories: list[CategorySpec]
    sections: list[SectionSpec]

    @property
    def seat_count(self) -> int:
        return sum(len(s.seats) for s in self.sections)

    def capacity(self, config: HallConfig) -> int:
        return sum(len(s.seats) for s in self.sections if config in s.configs)


CATEGORIES = [
    CategorySpec(1, "VIP", "#e8590c"),
    CategorySpec(2, "Фан-зона", "#f59f00"),
    CategorySpec(3, "Танцпол", "#1098ad"),
    CategorySpec(4, "Нижний ярус", "#7048e8"),
    CategorySpec(5, "Средний ярус", "#1c7ed6"),
    CategorySpec(6, "Верхний ярус", "#0ca678"),
]


def _fmt(value: float) -> str:
    return f"{value:.1f}"


# --- Периметр площадки ------------------------------------------------------------------


@dataclass(frozen=True)
class _Segment:
    """Участок периметра. Прямой — начало на борту, направление вдоль и наружу;
    угловой — центр дуги и начальный угол (дуга 90° по часовой стрелке)."""

    kind: str  # "straight" | "corner"
    origin: tuple[float, float] = (0.0, 0.0)
    along: tuple[float, float] = (0.0, 0.0)
    outward: tuple[float, float] = (0.0, 0.0)
    length: float = 0.0
    center: tuple[float, float] = (0.0, 0.0)
    start_angle: float = 0.0

    def point(self, d: float, t: float) -> tuple[float, float]:
        """Точка на расстоянии d от борта; t ∈ [0, 1] — доля длины сегмента."""
        if self.kind == "straight":
            ox, oy = self.origin
            return (
                ox + self.along[0] * t * self.length + self.outward[0] * d,
                oy + self.along[1] * t * self.length + self.outward[1] * d,
            )
        r = RINK_R + d
        angle = self.start_angle + t * math.pi / 2
        return self.center[0] + r * math.cos(angle), self.center[1] + r * math.sin(angle)

    def row_length(self, d: float) -> float:
        return self.length if self.kind == "straight" else (RINK_R + d) * math.pi / 2


_SA, _SB = RINK_A - RINK_R, RINK_B - RINK_R  # полудлины прямых участков борта
WEST_EXTENSION = RINK_R + 45  # на концерте длинные трибуны продолжаются до сцены

SEGMENTS = {
    "top": _Segment("straight", (CX - _SA, CY - RINK_B), (1, 0), (0, -1), 2 * _SA),
    "ne": _Segment("corner", center=(CX + _SA, CY - _SB), start_angle=-math.pi / 2),
    "east": _Segment("straight", (CX + RINK_A, CY - _SB), (0, 1), (1, 0), 2 * _SB),
    "se": _Segment("corner", center=(CX + _SA, CY + _SB), start_angle=0.0),
    "bottom": _Segment("straight", (CX + _SA, CY + RINK_B), (-1, 0), (0, 1), 2 * _SA),
    "sw": _Segment("corner", center=(CX - _SA, CY + _SB), start_angle=math.pi / 2),
    "west": _Segment("straight", (CX - RINK_A, CY + _SB), (0, -1), (-1, 0), 2 * _SB),
    "nw": _Segment("corner", center=(CX - _SA, CY - _SB), start_angle=math.pi),
    # Концертные продолжения длинных трибун к сцене (вместо западных углов и торца)
    "top_ext": _Segment(
        "straight", (CX - _SA - WEST_EXTENSION, CY - RINK_B), (1, 0), (0, -1), WEST_EXTENSION
    ),
    "bottom_ext": _Segment("straight", (CX - _SA, CY + RINK_B), (-1, 0), (0, 1), WEST_EXTENSION),
}

# Секторы по часовой стрелке от северо-запада: (сегмент, доля от, доля до, конфигурации)
SECTION_PLAN: list[tuple[str, float, float, tuple[HallConfig, ...]]] = [
    ("top_ext", 0.0, 1.0, STAGE_ONLY),
    ("top", 0.0, 0.25, BOTH),
    ("top", 0.25, 0.5, BOTH),
    ("top", 0.5, 0.75, BOTH),
    ("top", 0.75, 1.0, BOTH),
    ("ne", 0.0, 0.5, BOTH),
    ("ne", 0.5, 1.0, BOTH),
    ("east", 0.0, 1.0, BOTH),
    ("se", 0.0, 0.5, BOTH),
    ("se", 0.5, 1.0, BOTH),
    ("bottom", 0.0, 0.25, BOTH),
    ("bottom", 0.25, 0.5, BOTH),
    ("bottom", 0.5, 0.75, BOTH),
    ("bottom", 0.75, 1.0, BOTH),
    ("bottom_ext", 0.0, 1.0, STAGE_ONLY),
    ("sw", 0.0, 0.5, HOCKEY_ONLY),
    ("sw", 0.5, 1.0, HOCKEY_ONLY),
    ("west", 0.0, 1.0, HOCKEY_ONLY),
    ("nw", 0.0, 0.5, HOCKEY_ONLY),
    ("nw", 0.5, 1.0, HOCKEY_ONLY),
]


@dataclass(frozen=True)
class _Tier:
    number: int  # 1 — нижний, 2 — средний, 3 — верхний
    first_offset: float  # отступ первого ряда от борта
    rows: int
    category_id: int

    @property
    def last_offset(self) -> float:
        return self.first_offset + (self.rows - 1) * ROW_STEP


TIERS = [
    _Tier(1, 30.0, 10, 4),
    _Tier(2, 210.0, 7, 5),
    _Tier(3, 352.0, 7, 6),
]


def _category(tier: _Tier, segment: str, start: float) -> int:
    # Центр длинных сторон нижнего яруса — лучший вид и на лёд, и на сцену.
    if tier.number == 1 and segment in ("top", "bottom") and start in (0.25, 0.5):
        return 1
    return tier.category_id


def _trimmed(segment: _Segment, d: float, start: float, end: float, margin: float):
    length = segment.row_length(d)
    return start + margin / length, end - margin / length


def _section_path(segment: _Segment, start: float, end: float, d_in: float, d_out: float) -> str:
    t1, t2 = _trimmed(segment, d_in, start, end, HALF_AISLE - 3)
    u1, u2 = _trimmed(segment, d_out, start, end, HALF_AISLE - 3)
    a, b = segment.point(d_in, t1), segment.point(d_in, t2)
    c, e = segment.point(d_out, u2), segment.point(d_out, u1)
    if segment.kind == "straight":
        return (
            f"M {_fmt(a[0])} {_fmt(a[1])} L {_fmt(b[0])} {_fmt(b[1])} "
            f"L {_fmt(c[0])} {_fmt(c[1])} L {_fmt(e[0])} {_fmt(e[1])} Z"
        )
    r_in, r_out = RINK_R + d_in, RINK_R + d_out
    return (
        f"M {_fmt(a[0])} {_fmt(a[1])} "
        f"A {_fmt(r_in)} {_fmt(r_in)} 0 0 1 {_fmt(b[0])} {_fmt(b[1])} "
        f"L {_fmt(c[0])} {_fmt(c[1])} "
        f"A {_fmt(r_out)} {_fmt(r_out)} 0 0 0 {_fmt(e[0])} {_fmt(e[1])} Z"
    )


def _bowl_section(tier: _Tier, index: int, plan) -> SectionSpec:
    segment_name, start, end, configs = plan
    segment = SEGMENTS[segment_name]
    category = _category(tier, segment_name, start)

    seats: list[SeatSpec] = []
    for row in range(1, tier.rows + 1):
        d = tier.first_offset + (row - 1) * ROW_STEP
        length = segment.row_length(d)
        span = (end - start) * length - 2 * HALF_AISLE
        count = int(span // SEAT_PITCH) + 1
        first = (start + end) / 2 - (count - 1) * SEAT_PITCH / length / 2
        for number in range(1, count + 1):
            x, y = segment.point(d, first + (number - 1) * SEAT_PITCH / length)
            seats.append(SeatSpec(str(row), number, round(x, 1), round(y, 1), category))

    d_in, d_out = tier.first_offset - PAD, tier.last_offset + PAD
    # Подписи нижнего и среднего ярусов — в проходе к следующему ярусу, верхнего — снаружи.
    label_x, label_y = segment.point(d_out + 14, (start + end) / 2)
    code = f"{tier.number}{index:02d}"
    return SectionSpec(
        code=code,
        name=f"Сектор {code}",
        path=_section_path(segment, start, end, d_in, d_out),
        label_x=round(label_x, 1),
        label_y=round(label_y, 1),
        configs=configs,
        seats=seats,
    )


# --- Концертная конфигурация: сцена и стоячие зоны на льду -----------------------------

FLOOR_LEFT = CX - RINK_A  # на концерте лёд вплотную к сцене
FAN_ZONE_RIGHT = CX - RINK_A + 230
FAN_ZONE_CAPACITY = 500
DANCE_FLOOR_CAPACITY = 1500


def _stage_path() -> str:
    left, right = FLOOR_LEFT - 95, FLOOR_LEFT - 12
    top, bottom = CY - 150, CY + 150
    return (
        f"M {_fmt(left)} {_fmt(top)} H {_fmt(right - 20)} "
        f"Q {_fmt(right + 14)} {_fmt(CY)} {_fmt(right - 20)} {_fmt(bottom)} "
        f"H {_fmt(left)} Z"
    )


def _standing_section(
    code: str, name: str, path: str, x1: float, x2: float, capacity: int, category: int
) -> SectionSpec:
    cx = round((x1 + x2) / 2, 1)
    # Места стоячей зоны безымянные: номер — только внутренний идентификатор билета.
    seats = [SeatSpec("", n, cx, CY, category) for n in range(1, capacity + 1)]
    return SectionSpec(code, name, path, cx, CY, STAGE_ONLY, SectionKind.STANDING, seats)


def _floor_sections() -> list[SectionSpec]:
    top, bottom = CY - RINK_B, CY + RINK_B
    fan = (
        f"M {_fmt(FLOOR_LEFT)} {_fmt(top)} H {_fmt(FAN_ZONE_RIGHT)} "
        f"V {_fmt(bottom)} H {_fmt(FLOOR_LEFT)} Z"
    )
    right = CX + RINK_A
    dance = (
        f"M {_fmt(FAN_ZONE_RIGHT)} {_fmt(top)} H {_fmt(right - RINK_R)} "
        f"A {_fmt(RINK_R)} {_fmt(RINK_R)} 0 0 1 {_fmt(right)} {_fmt(top + RINK_R)} "
        f"V {_fmt(bottom - RINK_R)} "
        f"A {_fmt(RINK_R)} {_fmt(RINK_R)} 0 0 1 {_fmt(right - RINK_R)} {_fmt(bottom)} "
        f"H {_fmt(FAN_ZONE_RIGHT)} Z"
    )
    return [
        _standing_section("FAN", "Фан-зона", fan, FLOOR_LEFT, FAN_ZONE_RIGHT, FAN_ZONE_CAPACITY, 2),
        _standing_section(
            "DANCE", "Танцпол", dance, FAN_ZONE_RIGHT, right, DANCE_FLOOR_CAPACITY, 3
        ),
    ]


def build_arena() -> VenueSpec:
    bowl = [
        _bowl_section(tier, index, plan)
        for tier in TIERS
        for index, plan in enumerate(SECTION_PLAN, start=1)
    ]
    return VenueSpec(
        name="Арена «Северная»",
        address="г. Москва, Ленинградский пр-т (учебный адрес)",
        width=WIDTH,
        height=HEIGHT,
        rink=RinkSpec(CX - RINK_A, CY - RINK_B, 2 * RINK_A, 2 * RINK_B, RINK_R),
        stage_path=_stage_path(),
        categories=CATEGORIES,
        sections=_floor_sections() + bowl,
    )
