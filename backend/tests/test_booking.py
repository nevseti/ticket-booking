"""Бронирование: защита от двойной продажи и правила удержаний.

Конкурентные тесты запускают десятки корутин, у каждой — своя транзакция и своё соединение
с БД из пула. Корректность обеспечивает PostgreSQL (частичный уникальный индекс), поэтому
тесты идут только на настоящей БД.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import UnitOfWork
from app.core.errors import AppError
from app.modules.booking.service import BookingService
from app.modules.identity.security import create_access_token

STAGE_PRICES = [
    {"category_id": c, "price_kopecks": p}
    for c, p in [
        (1, 1_500_000),
        (2, 900_000),
        (3, 600_000),
        (4, 700_000),
        (5, 450_000),
        (6, 250_000),
    ]
]
HOCKEY_PRICES = [p for p in STAGE_PRICES if p["category_id"] in (1, 4, 5, 6)]


def auth() -> dict[str, str]:
    """Новый «пользователь»: токен с случайным id (авторизация не ходит в БД)."""
    return {"Authorization": f"Bearer {create_access_token(uuid.uuid4(), 'user')}"}


async def make_event(
    client: AsyncClient, admin_headers: dict[str, str], *, kind: str = "concert", **overrides: Any
) -> str:
    now = datetime.now(UTC)
    body = {
        "title": "Событие",
        "kind": kind,
        "starts_at": (now + timedelta(days=10)).isoformat(),
        "sales_start_at": (now - timedelta(hours=1)).isoformat(),
        "prices": HOCKEY_PRICES if kind == "sport" else STAGE_PRICES,
        **overrides,
    }
    resp = await client.post("/api/admin/events", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    event_id = resp.json()["id"]
    resp = await client.post(f"/api/admin/events/{event_id}/publish", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return event_id


@pytest.fixture
async def layout(client: AsyncClient) -> dict[str, Any]:
    data = (await client.get("/api/venue/layout")).json()
    codes = {s["id"]: s["code"] for s in data["sections"]}
    data["seats_in"] = lambda code: [
        s["id"] for s in data["seats"] if codes[s["section_id"]] == code
    ]
    data["zone"] = lambda name: next(s for s in data["sections"] if s["name"] == name)
    return data


@pytest.fixture
async def concert(client: AsyncClient, admin_headers: dict[str, str]) -> str:
    return await make_event(client, admin_headers)


async def hold(client: AsyncClient, event_id: str, seat_id: int, headers: dict[str, str]):
    return await client.post(
        f"/api/events/{event_id}/holds", json={"seat_id": seat_id}, headers=headers
    )


# --- Защита от двойной продажи -----------------------------------------------------------


async def test_concurrent_capture_has_single_winner(concert: str, layout: dict) -> None:
    """50 покупателей одновременно жмут на одно место — удержание получает ровно один."""
    seat_id = layout["seats_in"]("103")[0]
    event_id = uuid.UUID(concert)

    async def attempt() -> bool:
        async with UnitOfWork() as uow:
            try:
                await BookingService(uow).hold_seat(uuid.uuid4(), event_id, seat_id)
            except AppError as exc:
                assert exc.code == "SEAT_UNAVAILABLE"
                return False
            await uow.commit()
            return True

    results = await asyncio.gather(*(attempt() for _ in range(50)))

    assert results.count(True) == 1
    async with UnitOfWork() as uow:
        active = await uow.session.scalar(
            text("SELECT count(*) FROM booking.holds WHERE seat_id = :s AND status = 'active'"),
            {"s": seat_id},
        )
    assert active == 1


async def test_concurrent_zone_never_oversells(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    """90 покупателей по 6 билетов рвутся в фан-зону на 500 мест: продано ровно 500."""
    zone = layout["zone"]("Фан-зона")
    event_id = uuid.UUID(concert)

    async def attempt() -> int:
        async with UnitOfWork() as uow:
            try:
                holds = await BookingService(uow).hold_zone(uuid.uuid4(), event_id, zone["id"], 6)
            except AppError as exc:
                assert exc.code == "NOT_ENOUGH_PLACES"
                return 0
            await uow.commit()
            return len(holds)

    taken = sum(await asyncio.gather(*(attempt() for _ in range(90))))

    status = (await client.get(f"/api/events/{concert}/seatmap/status")).json()
    fan = next(z for z in status["zones"] if z["section_id"] == zone["id"])
    assert taken == fan["capacity"] - fan["available"]
    assert taken <= 500 and taken >= 498  # всё или ничего: остаток меньше 6 мест
    async with UnitOfWork() as uow:
        duplicates = await uow.session.scalar(
            text("""
                SELECT count(*) FROM (
                    SELECT seat_id FROM booking.holds WHERE status = 'active'
                    GROUP BY seat_id HAVING count(*) > 1
                ) d
            """)
        )
    assert duplicates == 0


async def test_sold_seat_cannot_be_held(client: AsyncClient, concert: str, layout: dict) -> None:
    seat_id = layout["seats_in"]("104")[0]
    async with UnitOfWork() as uow:
        await uow.session.execute(
            text("INSERT INTO booking.sold_seats VALUES (:e, :s, uuidv7(), now())"),
            {"e": concert, "s": seat_id},
        )
        await uow.commit()

    resp = await hold(client, concert, seat_id, auth())

    assert resp.status_code == 409
    assert resp.json()["code"] == "SEAT_UNAVAILABLE"


async def test_expired_hold_does_not_block_seat(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    seat_id = layout["seats_in"]("105")[0]
    first = await hold(client, concert, seat_id, auth())
    async with UnitOfWork() as uow:
        await uow.session.execute(
            text("UPDATE booking.holds SET expires_at = now() - interval '1 second'")
        )
        await uow.commit()

    second = await hold(client, concert, seat_id, auth())

    assert second.status_code == 201
    async with UnitOfWork() as uow:
        old_status = await uow.session.scalar(
            text("SELECT status FROM booking.holds WHERE id = :id"), {"id": first.json()["id"]}
        )
        expired_events = await uow.session.scalar(
            text("SELECT count(*) FROM infra.outbox WHERE event_type = 'booking.holds_expired'")
        )
    assert old_status == "expired"
    assert expired_events == 1


# --- Правила удержаний --------------------------------------------------------------------


async def test_hold_is_idempotent_for_owner_and_conflicts_for_others(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    seat_id = layout["seats_in"]("106")[0]
    me = auth()

    first = await hold(client, concert, seat_id, me)
    again = await hold(client, concert, seat_id, me)
    other = await hold(client, concert, seat_id, auth())

    assert first.status_code == 201
    body = first.json()
    assert body["seat_id"] == seat_id and body["section_name"] == "Сектор 106"
    assert body["price_kopecks"] > 0 and not body["standing"]
    assert again.json()["id"] == body["id"]  # двойной клик — то же удержание
    assert other.status_code == 409
    assert other.json()["code"] == "SEAT_UNAVAILABLE"


async def test_release_frees_the_seat(client: AsyncClient, concert: str, layout: dict) -> None:
    seat_id = layout["seats_in"]("107")[0]
    me, other = auth(), auth()
    hold_id = (await hold(client, concert, seat_id, me)).json()["id"]

    assert (await client.delete(f"/api/holds/{hold_id}", headers=other)).status_code == 404
    assert (await client.delete(f"/api/holds/{hold_id}", headers=me)).status_code == 204
    assert (await hold(client, concert, seat_id, other)).status_code == 201


async def test_hold_limit_per_user(client: AsyncClient, concert: str, layout: dict) -> None:
    seats = layout["seats_in"]("108")[:7]
    me = auth()
    for seat_id in seats[:6]:
        assert (await hold(client, concert, seat_id, me)).status_code == 201

    resp = await hold(client, concert, seats[6], me)

    assert resp.status_code == 409
    assert resp.json()["code"] == "HOLD_LIMIT"
    assert resp.json()["limit"] == 6


async def test_hall_config_decides_what_is_for_sale(
    client: AsyncClient, admin_headers: dict[str, str], concert: str, layout: dict
) -> None:
    hockey = await make_event(client, admin_headers, kind="sport", title="Хоккей")
    behind_stage = layout["seats_in"]("118")[0]  # западный торец
    fan_zone_seat = layout["zone"]("Фан-зона")["id"]

    on_concert = await hold(client, concert, behind_stage, auth())
    on_hockey = await hold(client, hockey, behind_stage, auth())
    zone_on_hockey = await client.post(
        f"/api/events/{hockey}/holds/zone",
        json={"section_id": fan_zone_seat, "quantity": 1},
        headers=auth(),
    )

    assert on_concert.status_code == 409
    assert on_concert.json()["code"] == "SEAT_NOT_FOR_SALE"
    assert on_hockey.status_code == 201
    assert zone_on_hockey.status_code == 409  # на хоккее на льду нет танцпола


async def test_sales_must_be_open(
    client: AsyncClient, admin_headers: dict[str, str], layout: dict
) -> None:
    later = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    event_id = await make_event(client, admin_headers, sales_start_at=later)

    resp = await hold(client, event_id, layout["seats_in"]("103")[0], auth())

    assert resp.status_code == 409
    assert resp.json()["code"] == "SALES_CLOSED"
    assert resp.json()["sale_status"] == "not_started"


async def test_standing_place_is_bought_by_quantity(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    zone = layout["zone"]("Танцпол")
    me = auth()

    resp = await client.post(
        f"/api/events/{concert}/holds/zone",
        json={"section_id": zone["id"], "quantity": 3},
        headers=me,
    )

    assert resp.status_code == 201
    holds = resp.json()
    assert len({h["seat_id"] for h in holds}) == 3
    assert all(h["standing"] and h["row"] is None for h in holds)
    # Безымянное место зоны нельзя выбрать «по номеру»
    direct = await hold(client, concert, holds[0]["seat_id"], auth())
    assert direct.status_code == 422 and direct.json()["code"] == "USE_ZONE_HOLD"

    mine = (await client.get(f"/api/events/{concert}/holds/my", headers=me)).json()
    assert len(mine["items"]) == 3
    assert mine["total_kopecks"] == 3 * 600_000
    assert mine["limit"] == 6 and mine["expires_at"] is not None

    status = (await client.get(f"/api/events/{concert}/seatmap/status")).json()
    dance = next(z for z in status["zones"] if z["section_id"] == zone["id"])
    assert dance["available"] == dance["capacity"] - 3


async def test_seatmap_status_and_release_all(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    seats = layout["seats_in"]("109")[:2]
    me = auth()
    for seat_id in seats:
        await hold(client, concert, seat_id, me)

    status = (await client.get(f"/api/events/{concert}/seatmap/status")).json()
    assert set(seats) <= set(status["held"])

    resp = await client.delete(f"/api/events/{concert}/holds/my", headers=me)
    assert resp.status_code == 204
    status = (await client.get(f"/api/events/{concert}/seatmap/status")).json()
    assert not set(seats) & set(status["held"])


async def test_holding_requires_login(client: AsyncClient, concert: str, layout: dict) -> None:
    resp = await client.post(
        f"/api/events/{concert}/holds", json={"seat_id": layout["seats_in"]("103")[0]}
    )

    assert resp.status_code == 401


async def test_hold_writes_outbox_event(client: AsyncClient, concert: str, layout: dict) -> None:
    seat_id = layout["seats_in"]("110")[0]

    await hold(client, concert, seat_id, auth())

    async with UnitOfWork() as uow:
        row = (
            await uow.session.execute(
                text("SELECT event_type, payload FROM infra.outbox ORDER BY id DESC LIMIT 1")
            )
        ).first()
    assert row.event_type == "booking.seats_held"
    assert row.payload == {"event_id": concert, "seat_ids": [seat_id]}
