import math
from collections import Counter
from itertools import pairwise

from app.modules.catalog.venue_layout import SEAT_PITCH, HallConfig, SectionKind, build_arena


def test_layout_is_deterministic() -> None:
    assert build_arena() == build_arena()


def test_seats_are_unique_and_inside_canvas() -> None:
    venue = build_arena()

    keys = [(s.code, seat.row, seat.number) for s in venue.sections for seat in s.seats]
    assert len(keys) == len(set(keys))
    for section in venue.sections:
        for seat in section.seats:
            assert 0 < seat.x < venue.width
            assert 0 < seat.y < venue.height


def test_seats_do_not_overlap_within_each_config() -> None:
    # Секторы западного торца (хоккей) и продолжения трибун к сцене (концерт) занимают
    # одно место на схеме, но никогда не продаются одновременно — проверяем по режимам.
    venue = build_arena()
    for config in HallConfig:
        points = [
            (seat.x, seat.y)
            for s in venue.sections
            if config in s.configs and s.kind == SectionKind.SEATED
            for seat in s.seats
        ]
        grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
        closest = math.inf
        for x, y in points:
            cell = (int(x // 20), int(y // 20))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for px, py in grid.get((cell[0] + dx, cell[1] + dy), []):
                        closest = min(closest, math.hypot(px - x, py - y))
            grid.setdefault(cell, []).append((x, y))
        assert closest >= SEAT_PITCH - 0.5, config


def test_configs_and_capacity() -> None:
    venue = build_arena()

    hockey = venue.capacity(HallConfig.HOCKEY)
    stage = venue.capacity(HallConfig.STAGE)
    assert 4000 <= hockey <= 6000
    assert stage > hockey  # на концерте добавляются стоячие зоны на льду
    standing = [s for s in venue.sections if s.kind == SectionKind.STANDING]
    assert {s.name for s in standing} == {"Фан-зона", "Танцпол"}
    assert all(s.configs == (HallConfig.STAGE,) for s in standing)


def test_categories_per_config() -> None:
    venue = build_arena()

    def categories(config: HallConfig) -> set[int]:
        return {seat.category_id for s in venue.sections if config in s.configs for seat in s.seats}

    assert categories(HallConfig.HOCKEY) == {1, 4, 5, 6, 7}
    assert categories(HallConfig.STAGE) == {1, 2, 3, 4, 5, 6, 7}
    tiers = Counter(s.code[0] for s in venue.sections if s.kind == SectionKind.SEATED)
    # 20 секторов в каждом ярусе; премиальное кольцо — VIP на длинных сторонах, лаунж на торцах
    assert tiers == {"1": 20, "2": 20, "3": 20, "V": 10, "L": 10}


def test_premium_ring_and_boxes() -> None:
    venue = build_arena()
    vip = [s for s in venue.sections if s.code.startswith("V")]
    lounge = [s for s in venue.sections if s.code.startswith("L")]

    assert {seat.category_id for s in vip for seat in s.seats} == {1}
    assert {seat.category_id for s in lounge for seat in s.seats} == {7}
    assert all({seat.row for seat in s.seats} == {"1", "2"} for s in vip + lounge)
    assert venue.boxes and all(0 < b.y < venue.height for b in venue.boxes)


def test_rows_span_the_whole_section() -> None:
    """Ровные края: крайние места каждого ряда на одном расстоянии от границ сектора."""
    from app.modules.catalog.venue_layout import SEAT_PITCH as pitch

    venue = build_arena()
    section = next(s for s in venue.sections if s.code == "106")  # веерный угловой сектор
    rows: dict[str, list] = {}
    for seat in section.seats:
        rows.setdefault(seat.row, []).append(seat)
    for seats in rows.values():
        gaps = [((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5 for a, b in pairwise(seats)]
        assert max(gaps) - min(gaps) < 0.5  # внутри ряда шаг одинаковый
        assert min(gaps) >= pitch - 0.2
