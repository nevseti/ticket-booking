"""Ограничение частоты: token bucket в Redis, лимиты на пользователя и на IP."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import ratelimit
from app.core.config import settings
from app.core.ratelimit import Rule, hit
from tests.test_booking import auth, concert, hold, layout

__all__ = ["concert", "layout"]


@pytest.fixture(autouse=True)
def limits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)


async def test_bucket_allows_burst_then_refills() -> None:
    rule = Rule("test", capacity=3, per_seconds=0.3)  # жетон каждые 100 мс
    subject = uuid.uuid4().hex

    burst = [(await hit(rule, subject)).allowed for _ in range(4)]
    await asyncio.sleep(0.15)
    after_pause = await hit(rule, subject)

    assert burst == [True, True, True, False]
    assert after_pause.allowed


async def test_subjects_have_separate_buckets() -> None:
    rule = Rule("test", capacity=1, per_seconds=60)

    assert (await hit(rule, "a")).allowed
    assert not (await hit(rule, "a")).allowed
    assert (await hit(rule, "b")).allowed


async def test_login_is_limited_by_ip(client: AsyncClient) -> None:
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    codes = [
        (await client.post("/api/auth/login", json=body)).status_code
        for _ in range(ratelimit.AUTH.capacity + 1)
    ]

    assert codes[:-1] == [401] * ratelimit.AUTH.capacity
    blocked = await client.post("/api/auth/login", json=body)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) == blocked.json()["retry_after"] >= 1


async def test_holds_are_limited_per_user_not_globally(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    """Скрипт, кликающий по местам без остановки, упирается в лимит — другие покупатели нет."""
    greedy, other = auth(), auth()
    seats = layout["seats_in"]("103")

    codes = []
    for seat_id in seats[: ratelimit.HOLDS.capacity + 1]:
        resp = await hold(client, concert, seat_id, greedy)
        codes.append(resp.status_code)
        if resp.status_code == 201:  # освобождаем, чтобы не упереться в лимит 6 мест
            # (освобождение тоже тратит жетон)
            await client.delete(f"/api/holds/{resp.json()['id']}", headers=greedy)

    assert 429 in codes
    assert (await hold(client, concert, seats[-1], other)).status_code == 201


async def test_redis_failure_does_not_block_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(*args: object, **kwargs: object) -> None:
        raise RedisConnectionError("redis is down")

    monkeypatch.setattr(ratelimit, "_bucket", broken)

    assert (await hit(Rule("test", capacity=1, per_seconds=60), "x")).allowed
