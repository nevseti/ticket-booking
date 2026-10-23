"""Модель чтения схемы зала в Redis (CQRS) и раздача изменений по SSE."""

import asyncio
import json
import uuid

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.db import UnitOfWork
from app.core.redis import redis_client
from app.modules.booking import facade as booking
from app.modules.booking import live, seatmap_view
from app.modules.booking.live import RESYNC, Frame, SeatmapHub
from app.modules.catalog import facade as catalog
from tests.test_booking import auth, concert, hold, layout, sync_seatmap
from tests.test_orders import pay

__all__ = ["concert", "layout"]


async def from_redis(event_id: str) -> dict:
    async with UnitOfWork() as uow:
        return (await seatmap_view.read_status(uow, uuid.UUID(event_id))).model_dump()


async def from_db(event_id: str) -> dict:
    async with UnitOfWork() as uow:
        return (await seatmap_view.status_from_db(uow, uuid.UUID(event_id))).model_dump()


def same_state(a: dict, b: dict) -> bool:
    return {**a, "version": 0} == {**b, "version": 0}


async def test_projection_follows_all_kinds_of_changes(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    """Проекция строится до изменений, затем живёт только событиями — и совпадает с БД."""
    await from_redis(concert)  # проекция построена по пустому залу

    buyer, holder = auth(), auth()
    vip = layout["seats_in"]("103")[:3]
    for seat_id in vip[:2]:
        await hold(client, concert, seat_id, buyer)
    dance = layout["zone"]("Танцпол")
    await client.post(
        f"/api/events/{concert}/holds/zone",
        json={"section_id": dance["id"], "quantity": 2},
        headers=buyer,
    )
    assert (await pay(client, concert, buyer)).json()["state"] == "completed"
    resp = await hold(client, concert, vip[2], holder)
    await client.delete(f"/api/holds/{resp.json()['id']}", headers=holder)
    fan = layout["zone"]("Фан-зона")
    await client.post(
        f"/api/events/{concert}/holds/zone",
        json={"section_id": fan["id"], "quantity": 4},
        headers=holder,
    )

    await sync_seatmap()
    projected = await from_redis(concert)

    assert same_state(projected, await from_db(concert))
    assert set(vip[:2]) <= set(projected["sold"]) and vip[2] not in projected["held"]
    zones = {z["section_id"]: z for z in projected["zones"]}
    assert zones[dance["id"]]["capacity"] - zones[dance["id"]]["available"] == 2
    assert zones[fan["id"]]["capacity"] - zones[fan["id"]]["available"] == 4


async def test_repeated_events_change_nothing(concert: str, layout: dict) -> None:
    """Outbox доставляет «хотя бы один раз»: повтор события не сдвигает ни места, ни версию."""
    seat_id = layout["seats_in"]("104")[0]
    zone = layout["zone"]("Фан-зона")
    async with UnitOfWork() as uow:
        zone_seat = min((await catalog.standing_seat_ids(uow))[zone["id"]])
    await from_redis(concert)
    payload = {"event_id": concert, "seat_ids": [seat_id, zone_seat]}

    first = await booking.project_seatmap_event("booking.seats_held", payload)
    again = await booking.project_seatmap_event("booking.seats_held", payload)

    assert again == first
    status = await from_redis(concert)
    fan = next(z for z in status["zones"] if z["section_id"] == zone["id"])
    assert status["held"] == [seat_id] and fan["capacity"] - fan["available"] == 1

    await booking.project_seatmap_event("booking.seats_sold", payload)
    await booking.project_seatmap_event("booking.holds_expired", payload)  # опоздавшее событие
    status = await from_redis(concert)
    fan = next(z for z in status["zones"] if z["section_id"] == zone["id"])
    assert status["sold"] == [seat_id] and status["held"] == []
    assert fan["capacity"] - fan["available"] == 1  # проданное место не освобождается


async def test_missing_projection_is_rebuilt_by_the_event(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    seats = layout["seats_in"]("105")[:2]
    await hold(client, concert, seats[0], auth())
    await sync_seatmap()
    await redis_client.delete(seatmap_view.projection_key(uuid.UUID(concert)))  # «вытеснена»

    await hold(client, concert, seats[1], auth())
    await sync_seatmap()

    assert await redis_client.exists(seatmap_view.projection_key(uuid.UUID(concert)))
    assert set(seats) <= set((await from_redis(concert))["held"])


async def test_versions_grow_by_one_per_change(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    start = (await from_redis(concert))["version"]
    for seat_id in layout["seats_in"]("106")[:3]:
        await hold(client, concert, seat_id, auth())
    await sync_seatmap()

    assert (await from_redis(concert))["version"] == start + 3


async def test_db_mode_reads_postgres_without_version(
    client: AsyncClient, concert: str, layout: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Переключатель для эксперимента «Redis против БД» в нагрузочном тесте."""
    monkeypatch.setattr(settings, "seatmap_read_model", "db")
    seat_id = layout["seats_in"]("107")[0]
    await hold(client, concert, seat_id, auth())

    status = (await client.get(f"/api/events/{concert}/seatmap/status")).json()

    assert status["version"] == 0 and status["held"] == [seat_id]


# --- SSE ----------------------------------------------------------------------------------


async def _wait_hub_listening() -> None:
    for _ in range(100):
        if await redis_client.execute_command("PUBSUB", "NUMPAT"):
            return
        await asyncio.sleep(0.02)
    raise AssertionError("хаб не подписался на Redis")


async def test_stream_delivers_deltas(client: AsyncClient, concert: str, layout: dict) -> None:
    await from_redis(concert)
    stream = live.sse_stream(uuid.UUID(concert))
    assert (await anext(stream)).startswith("retry:")
    await _wait_hub_listening()
    seat_id = layout["seats_in"]("108")[0]

    await hold(client, concert, seat_id, auth())
    await sync_seatmap()
    chunk = await asyncio.wait_for(anext(stream), timeout=5)
    await stream.aclose()

    event, data = chunk.strip().split("\n")
    assert event == "event: delta"
    delta = json.loads(data.removeprefix("data: "))
    assert delta["seats"] == {str(seat_id): "h"}
    assert delta["v"] == (await from_redis(concert))["version"]
    assert live.hub.viewers == 0  # закрытый поток отписался


async def test_stream_for_unknown_event_is_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/events/{uuid.uuid4()}/seatmap/stream")

    assert resp.status_code == 404
    assert resp.json()["code"] == "EVENT_NOT_FOUND"


def test_slow_viewer_gets_resync_instead_of_backlog() -> None:
    hub = SeatmapHub(redis_client)
    event_id = uuid.uuid4()
    queue = asyncio.Queue[Frame](maxsize=2)
    hub._subscribers[str(event_id)] = {queue}

    for v in range(5):
        hub.deliver(str(event_id), Frame("delta", json.dumps({"v": v})))

    # Очередь переполнилась → накопленное выброшено, вместо него одно «перечитай снимок».
    assert queue.get_nowait() == RESYNC and queue.empty()
