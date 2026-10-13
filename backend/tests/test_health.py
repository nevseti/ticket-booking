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
