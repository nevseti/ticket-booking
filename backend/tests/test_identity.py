import uuid
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import register_error_handlers
from app.modules.identity.facade import AuthUser, require_admin
from app.modules.identity.security import create_access_token, hash_password, verify_password

PASSWORD = "correct-horse-battery"


async def register(client: AsyncClient, email: str = "anna@example.com", **extra: str):
    payload = {"email": email, "name": "Анна", "password": PASSWORD, **extra}
    return await client.post("/api/auth/register", json=payload)


async def test_register_logs_user_in(client: AsyncClient) -> None:
    resp = await register(client, email="Anna@Example.com")

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "anna@example.com"  # email нормализуется
    assert body["role"] == "user"
    assert "password_hash" not in body

    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/api" in cookie

    me = await client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["id"] == body["id"]


async def test_register_duplicate_email_is_case_insensitive(client: AsyncClient) -> None:
    await register(client, email="anna@example.com")

    resp = await register(client, email="ANNA@example.com")

    assert resp.status_code == 409
    assert resp.json()["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize(
    ("field", "value"),
    [("password", "short"), ("email", "not-an-email"), ("name", "   ")],
)
async def test_register_validation(client: AsyncClient, field: str, value: str) -> None:
    resp = await register(client, **{field: value})

    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


async def test_login_and_logout(client: AsyncClient) -> None:
    await register(client)
    client.cookies.clear()
    assert (await client.get("/api/me")).status_code == 401

    resp = await client.post(
        "/api/auth/login", json={"email": "anna@example.com", "password": PASSWORD}
    )
    assert resp.status_code == 200
    assert (await client.get("/api/me")).status_code == 200

    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/me")).status_code == 401


@pytest.mark.parametrize("email", ["anna@example.com", "nobody@example.com"])
async def test_login_rejects_bad_credentials_uniformly(client: AsyncClient, email: str) -> None:
    await register(client)
    client.cookies.clear()

    resp = await client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"})

    # Одинаковый ответ для «нет такого email» и «неверный пароль»:
    # не раскрываем, кто зарегистрирован.
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


async def test_bearer_token_is_accepted(client: AsyncClient) -> None:
    user_id = (await register(client)).json()["id"]
    client.cookies.clear()

    token = create_access_token(user_id=uuid.UUID(user_id), role="user")
    resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


async def test_tampered_token_is_rejected(client: AsyncClient) -> None:
    await register(client)
    token = client.cookies.get("access_token")
    assert token
    client.cookies.clear()

    resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token[:-2]}xx"})

    assert resp.status_code == 401


def test_password_hashing() -> None:
    hashed = hash_password(PASSWORD)

    assert hashed.startswith("$argon2id$")
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("other-password", hashed)
    assert not verify_password(PASSWORD, None)


async def test_require_admin_dependency() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/admin-only")
    async def admin_only(user: Annotated[AuthUser, Depends(require_admin)]) -> dict[str, str]:
        return {"id": str(user.id)}

    uid = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        anon = await ac.get("/admin-only")
        as_user = await ac.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {create_access_token(uid, 'user')}"},
        )
        as_admin = await ac.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {create_access_token(uid, 'admin')}"},
        )

    assert anon.status_code == 401
    assert as_user.status_code == 403
    assert as_admin.status_code == 200
