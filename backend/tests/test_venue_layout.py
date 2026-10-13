import math
from collections import Counter

from app.modules.catalog.venue_layout import SEAT_PITCH, build_arena


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


def test_seats_do_not_overlap() -> None:
    points = [(seat.x, seat.y) for s in build_arena().sections for seat in s.seats]
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    closest = math.inf
    for x, y in points:
        cell = (int(x // 20), int(y // 20))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py in grid.get((cell[0] + dx, cell[1] + dy), []):
                    closest = min(closest, math.hypot(px - x, py - y))
        grid.setdefault(cell, []).append((x, y))

    assert closest >= SEAT_PITCH - 0.5


def test_capacity_and_categories() -> None:
    venue = build_arena()
    by_category = Counter(seat.category_id for s in venue.sections for seat in s.seats)

    assert 2500 <= venue.seat_count <= 3200  # достаточно для конкуренции в нагрузочном тесте
    assert set(by_category) == {c.id for c in venue.categories}
    assert len({s.code for s in venue.sections}) == len(venue.sections)
