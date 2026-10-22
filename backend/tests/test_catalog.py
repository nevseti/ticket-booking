import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import UnitOfWork
from app.modules.catalog import facade as catalog
from app.modules.catalog.seed import DEMO_EVENTS, seed_demo_events, seed_venue
from app.modules.catalog.venue_layout import build_arena

ALL_PRICES = [
    {"category_id": 1, "price_kopecks": 900_000},
    {"category_id": 2, "price_kopecks": 500_000},
    {"category_id": 3, "price_kopecks": 300_000},
    {"category_id": 4, "price_kopecks": 150_000},
]


def payload(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    body = {
        "title": "Концерт",
        "description": "Описание",
        "kind": "concert",
        "starts_at": (now + timedelta(days=10)).isoformat(),
        "sales_start_at": (now - timedelta(hours=1)).isoformat(),
        "prices": ALL_PRICES,
    }
    body.update(overrides)
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
    assert len(layout["seats"]) == spec.seat_count
    assert len(layout["sections"]) == len(spec.sections)
    assert [c["name"] for c in layout["categories"]] == ["VIP", "Партер", "Амфитеатр", "Балкон"]
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
    event = await create_event(client, admin_headers, publish=False, prices=ALL_PRICES[:2])

    resp = await client.post(f"/api/admin/events/{event['id']}/publish", headers=admin_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "PRICES_INCOMPLETE"
    assert resp.json()["missing_category_ids"] == [3, 4]


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
    assert card["min_price_kopecks"] == 150_000

    detail = (await client.get(f"/api/events/{event['id']}")).json()
    assert [p["category_name"] for p in detail["prices"]] == [
        "VIP",
        "Партер",
        "Амфитеатр",
        "Балкон",
    ]
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
        ({"prices": [ALL_PRICES[0], ALL_PRICES[0]]}, "VALIDATION_ERROR"),
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
        json=payload(title="Новое название", prices=ALL_PRICES[:1] + ALL_PRICES[1:]),
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
    event = await create_event(client, admin_headers)
    event_id = uuid.UUID(event["id"])

    async with UnitOfWork() as uow:
        info = await catalog.get_event(uow, event_id)
        prices = await catalog.get_prices(uow, event_id)
        seats = await catalog.get_seats(uow, [1, 2, 10**9])
        missing = await catalog.get_event(uow, uuid.uuid4())

    assert info is not None and info.on_sale
    assert prices == {1: 900_000, 2: 500_000, 3: 300_000, 4: 150_000}
    assert set(seats) == {1, 2}  # несуществующее место отброшено
    assert seats[1].section_code == "P1" and seats[1].row == "1" and seats[1].number == 1
    assert missing is None
