import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import UnitOfWork
from app.modules.catalog import facade as catalog
from app.modules.catalog.seed import DEMO_EVENTS, seed_demo_events, seed_venue
from app.modules.catalog.venue_layout import HallConfig, SectionKind, build_arena

# Концерт/шоу (режим «сцена»): VIP, фан-зона, танцпол, нижний, средний, верхний ярус.
STAGE_PRICES = [
    {"category_id": 1, "price_kopecks": 1_500_000},
    {"category_id": 2, "price_kopecks": 900_000},
    {"category_id": 3, "price_kopecks": 600_000},
    {"category_id": 4, "price_kopecks": 700_000},
    {"category_id": 5, "price_kopecks": 450_000},
    {"category_id": 6, "price_kopecks": 250_000},
    {"category_id": 7, "price_kopecks": 1_100_000},
]
# Хоккей: партера на льду нет — только VIP и ярусы.
HOCKEY_PRICES = [p for p in STAGE_PRICES if p["category_id"] in (1, 4, 5, 6, 7)]
STAGE_CATEGORY_NAMES = [
    "VIP",
    "Фан-зона",
    "Танцпол",
    "Нижний ярус",
    "Средний ярус",
    "Верхний ярус",
    "Лаунж",
]


def payload(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    body = {
        "title": "Концерт",
        "description": "Описание",
        "kind": "concert",
        "starts_at": (now + timedelta(days=10)).isoformat(),
        "sales_start_at": (now - timedelta(hours=1)).isoformat(),
    }
    body.update(overrides)
    body.setdefault("prices", HOCKEY_PRICES if body["kind"] == "sport" else STAGE_PRICES)
    return body


async def create_event(
    client: AsyncClient, headers: dict[str, str], *, publish: bool = True, **overrides: Any
) -> dict[str, Any]:
    resp = await client.post("/api/admin/events", json=payload(**overrides), headers=headers)
    assert resp.status_code == 201, resp.text
    event = resp.json()
    if publish:
        resp = await client.post(f"/api/admin/events/{event['id']}/publish", headers=headers)
        assert resp.status_code == 200, resp.text
        event = resp.json()
    return event


# --- Схема зала --------------------------------------------------------------------------


async def test_layout_matches_generator_and_supports_etag(client: AsyncClient) -> None:
    spec = build_arena()

    resp = await client.get("/api/venue/layout")

    assert resp.status_code == 200
    layout = resp.json()
    seated = sum(len(s.seats) for s in spec.sections if s.kind == SectionKind.SEATED)
    assert len(layout["seats"]) == seated  # места стоячих зон на схеме не рисуются
    assert len(layout["sections"]) == len(spec.sections)
    assert [c["name"] for c in layout["categories"]] == STAGE_CATEGORY_NAMES
    configs = {c["id"]: c for c in layout["hall_configs"]}
    assert configs["hockey"]["capacity"] == spec.capacity(HallConfig.HOCKEY)
    assert configs["hockey"]["category_ids"] == [1, 4, 5, 6, 7]
    assert configs["stage"]["category_ids"] == [1, 2, 3, 4, 5, 6, 7]
    standing = [s for s in layout["sections"] if s["kind"] == "standing"]
    assert {s["name"]: s["capacity"] for s in standing} == {"Фан-зона": 500, "Танцпол": 1500}
    assert "max-age" in resp.headers["cache-control"]

    cached = await client.get("/api/venue/layout", headers={"If-None-Match": resp.headers["etag"]})
    assert cached.status_code == 304


async def test_seed_venue_is_idempotent() -> None:
    async with UnitOfWork() as uow:
        assert await seed_venue(uow.session) == 0


# --- Права ------------------------------------------------------------------------------


async def test_admin_endpoints_require_admin(
    client: AsyncClient, user_headers: dict[str, str]
) -> None:
    assert (await client.post("/api/admin/events", json=payload())).status_code == 401
    resp = await client.post("/api/admin/events", json=payload(), headers=user_headers)
    assert resp.status_code == 403


# --- Жизненный цикл мероприятия ----------------------------------------------------------


async def test_draft_is_hidden_from_public(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    event = await create_event(client, admin_headers, publish=False)

    assert event["status"] == "draft"
    assert event["sale_status"] == "draft"
    assert (await client.get("/api/events")).json()["total"] == 0
    assert (await client.get(f"/api/events/{event['id']}")).status_code == 404
    resp = await client.get(f"/api/events/{event['id']}", headers=admin_headers)
    assert resp.status_code == 200


async def test_publish_requires_all_prices(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    event = await create_event(client, admin_headers, publish=False, prices=STAGE_PRICES[:2])

    resp = await client.post(f"/api/admin/events/{event['id']}/publish", headers=admin_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "PRICES_INCOMPLETE"
    assert resp.json()["missing_category_ids"] == [3, 4, 5, 6, 7]


async def test_hockey_uses_hockey_categories(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    event = await create_event(client, admin_headers, kind="sport", title="Хоккей")

    assert event["hall_config"] == "hockey"
    assert [p["category_name"] for p in event["prices"]] == [
        "VIP",
        "Нижний ярус",
        "Средний ярус",
        "Верхний ярус",
        "Лаунж",
    ]
    # Цена на фан-зону и танцпол для хоккея бессмысленна: партера на льду нет.
    resp = await client.post(
        "/api/admin/events", json=payload(kind="sport", prices=STAGE_PRICES), headers=admin_headers
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "UNKNOWN_PRICE_CATEGORY"
    assert resp.json()["category_ids"] == [2, 3]


async def test_published_event_in_listing(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    event = await create_event(client, admin_headers)

    assert event["status"] == "published"
    assert event["published_at"] is not None
    listing = (await client.get("/api/events")).json()
    assert listing["total"] == 1
    card = listing["items"][0]
    assert card["id"] == event["id"]
    assert card["sale_status"] == "on_sale"
    assert card["min_price_kopecks"] == 250_000
    assert card["hall_config"] == "stage"

    detail = (await client.get(f"/api/events/{event['id']}")).json()
    assert [p["category_name"] for p in detail["prices"]] == STAGE_CATEGORY_NAMES
    assert detail["venue"]["name"]
    assert detail["sales_end_at"] == detail["starts_at"]  # по умолчанию — до начала


async def test_sale_status_not_started(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    later = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    event = await create_event(client, admin_headers, sales_start_at=later)

    assert event["sale_status"] == "not_started"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        (
            {"sales_start_at": (datetime.now(UTC) + timedelta(days=20)).isoformat()},
            "VALIDATION_ERROR",
        ),
        ({"prices": [STAGE_PRICES[0], STAGE_PRICES[0]]}, "VALIDATION_ERROR"),
        ({"starts_at": "2026-12-01T19:00:00"}, "VALIDATION_ERROR"),  # без часового пояса
        ({"prices": [{"category_id": 99, "price_kopecks": 100}]}, "UNKNOWN_PRICE_CATEGORY"),
        ({"title": "   "}, "VALIDATION_ERROR"),
    ],
)
async def test_event_validation(
    client: AsyncClient, admin_headers: dict[str, str], overrides: dict[str, Any], code: str
) -> None:
    resp = await client.post("/api/admin/events", json=payload(**overrides), headers=admin_headers)

    assert resp.status_code == 422
    assert resp.json()["code"] == code


async def test_update_event(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    event = await create_event(client, admin_headers)

    resp = await client.put(
        f"/api/admin/events/{event['id']}",
        json=payload(title="Новое название"),
        headers=admin_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["title"] == "Новое название"
    assert resp.json()["status"] == "published"


async def test_cancel_event(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    event = await create_event(client, admin_headers)

    resp = await client.post(f"/api/admin/events/{event['id']}/cancel", headers=admin_headers)

    assert resp.json()["sale_status"] == "cancelled"
    assert (await client.get("/api/events")).json()["total"] == 0
    assert (await client.get(f"/api/events/{event['id']}")).json()["sale_status"] == "cancelled"
    edit = await client.put(
        f"/api/admin/events/{event['id']}", json=payload(), headers=admin_headers
    )
    assert edit.status_code == 409
    assert edit.json()["code"] == "EVENT_CANCELLED"


async def test_listing_filters_and_pagination(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    now = datetime.now(UTC)
    await create_event(client, admin_headers, title="Хоккей: финал", kind="sport")
    await create_event(client, admin_headers, title="Джаз", kind="concert")
    await create_event(client, admin_headers, title="Рок", kind="concert")
    await create_event(
        client,
        admin_headers,
        title="Прошедший концерт",
        starts_at=(now - timedelta(days=1)).isoformat(),
        sales_start_at=(now - timedelta(days=5)).isoformat(),
    )

    async def titles(**params: Any) -> list[str]:
        resp = await client.get("/api/events", params=params)
        return [e["title"] for e in resp.json()["items"]]

    assert len(await titles()) == 3  # прошедшее скрыто
    assert len(await titles(include_past=True)) == 4
    assert await titles(kind="sport") == ["Хоккей: финал"]
    assert await titles(q="ХОККЕЙ") == ["Хоккей: финал"]
    page = (await client.get("/api/events", params={"page": 2, "page_size": 2})).json()
    assert page["total"] == 3 and len(page["items"]) == 1


async def test_admin_listing_includes_drafts(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await create_event(client, admin_headers, publish=False, title="Черновик")
    await create_event(client, admin_headers, title="Опубликовано")

    all_events = (await client.get("/api/admin/events", headers=admin_headers)).json()
    drafts = (
        await client.get("/api/admin/events", params={"status": "draft"}, headers=admin_headers)
    ).json()

    assert all_events["total"] == 2
    assert [e["title"] for e in drafts["items"]] == ["Черновик"]


async def test_unknown_event_is_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/events/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["code"] == "EVENT_NOT_FOUND"


# --- Демо-данные и фасад -----------------------------------------------------------------


async def test_seed_demo_events_once() -> None:
    async with UnitOfWork() as uow:
        created = await seed_demo_events(uow.session, datetime.now(UTC))
        again = await seed_demo_events(uow.session, datetime.now(UTC))
        await uow.commit()

    assert created == len(DEMO_EVENTS)
    assert again == 0


async def test_facade(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    concert = await create_event(client, admin_headers)
    hockey = await create_event(client, admin_headers, kind="sport", title="Хоккей")
    layout = (await client.get("/api/venue/layout")).json()
    codes = {s["id"]: s["code"] for s in layout["sections"]}
    west_end = next(s for s in layout["seats"] if codes[s["section_id"]] == "118")  # за сценой
    side = next(s for s in layout["seats"] if codes[s["section_id"]] == "103")  # вдоль борта

    async with UnitOfWork() as uow:
        concert_info = await catalog.get_event(uow, uuid.UUID(concert["id"]))
        hockey_info = await catalog.get_event(uow, uuid.UUID(hockey["id"]))
        prices = await catalog.get_prices(uow, uuid.UUID(concert["id"]))
        seats = await catalog.get_seats(uow, [west_end["id"], side["id"], 10**9])
        missing = await catalog.get_event(uow, uuid.uuid4())

    assert concert_info is not None and concert_info.on_sale
    assert hockey_info is not None and hockey_info.hall_config == HallConfig.HOCKEY
    assert prices == {p["category_id"]: p["price_kopecks"] for p in STAGE_PRICES}
    assert set(seats) == {west_end["id"], side["id"]}  # несуществующее место отброшено
    # Западный торец закрыт сценой на концерте, но продаётся на хоккее.
    assert not concert_info.sells(seats[west_end["id"]])
    assert hockey_info.sells(seats[west_end["id"]])
    assert concert_info.sells(seats[side["id"]]) and hockey_info.sells(seats[side["id"]])
    assert missing is None


async def test_relayout_moves_sold_seats_to_same_address() -> None:
    """Перестройка зала (новая версия схемы) переносит проданное место на место с тем же
    адресом «сектор, ряд, номер» и добавляет цену новой категории мероприятиям."""
    import uuid

    from sqlalchemy import text

    from app.core.db import UnitOfWork
    from app.modules.catalog.seed import seed_venue

    async with UnitOfWork() as uow:
        seat_id, code, row, number = (
            await uow.session.execute(
                text("""
                    SELECT s.id, sec.code, s.row, s.number FROM catalog.seats s
                    JOIN catalog.sections sec ON sec.id = s.section_id
                    WHERE sec.code = '104' AND s.row = '3' AND s.number = 5
                """)
            )
        ).one()
        event_id = uuid.uuid4()
        await uow.session.execute(
            text("INSERT INTO booking.sold_seats VALUES (:e, :s, :o)"),
            {"e": event_id, "s": seat_id, "o": uuid.uuid4()},
        )
        # Схема «устарела»: seed-venue должен её перестроить.
        await uow.session.execute(text("UPDATE catalog.venues SET layout_version = 1"))
        await uow.commit()

    async with UnitOfWork() as uow:
        created = await seed_venue(uow.session)
        await uow.commit()

    async with UnitOfWork() as uow:
        moved_to = await uow.session.scalar(
            text("SELECT seat_id FROM booking.sold_seats WHERE event_id = :e"), {"e": event_id}
        )
        address = (
            await uow.session.execute(
                text("""
                    SELECT sec.code, s.row, s.number FROM catalog.seats s
                    JOIN catalog.sections sec ON sec.id = s.section_id WHERE s.id = :id
                """),
                {"id": moved_to},
            )
        ).one()
        version = await uow.session.scalar(text("SELECT layout_version FROM catalog.venues"))
    assert created > 0 and moved_to != seat_id
    assert tuple(address) == (code, row, number)
    assert version >= 2


async def test_refresh_demo_dates_moves_events_forward_without_deleting() -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from app.core.db import UnitOfWork
    from app.modules.catalog.models import Event
    from app.modules.catalog.seed import refresh_demo_dates, seed_demo_events

    long_ago = datetime.now(UTC) - timedelta(days=200)
    async with UnitOfWork() as uow:
        await seed_demo_events(uow.session, long_ago)
        await uow.commit()
    async with UnitOfWork() as uow:
        ids_before = set(await uow.session.scalars(select(Event.id)))
        updated = await refresh_demo_dates(uow.session, datetime.now(UTC))
        await uow.commit()
    async with UnitOfWork() as uow:
        ids_after = set(await uow.session.scalars(select(Event.id)))
        earliest = await uow.session.scalar(select(func.min(Event.starts_at)))

    assert updated == len(ids_before) and ids_after == ids_before
    assert earliest > datetime.now(UTC)
