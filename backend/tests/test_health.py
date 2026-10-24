from httpx import AsyncClient


async def test_health_returns_version(client: AsyncClient) -> None:
    resp = await client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"
    assert "version" in body


async def test_ready_checks_dependencies(client: AsyncClient) -> None:
    resp = await client.get("/api/ready")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"postgres": True, "redis": True}}


async def test_request_id_is_echoed(client: AsyncClient) -> None:
    resp = await client.get("/api/health", headers={"X-Request-ID": "abc123"})

    assert resp.headers["x-request-id"] == "abc123"


async def test_unknown_route_returns_problem_json(client: AsyncClient) -> None:
    resp = await client.get("/api/nope")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["status"] == 404


async def test_pool_exhaustion_is_503_not_500() -> None:
    """Перегрузка БД (все соединения заняты) — честный 503 с Retry-After, а не 500."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.exc import TimeoutError as PoolTimeoutError

    from app.core.errors import register_error_handlers

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/overloaded")
    async def overloaded() -> None:
        raise PoolTimeoutError("QueuePool limit reached")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/overloaded")

    assert resp.status_code == 503
    assert resp.json()["code"] == "SERVICE_OVERLOADED"
    assert resp.headers["Retry-After"] == "2"
