"""Публичный интерфейс модуля identity. Только его могут вызывать другие модули.

- FastAPI-зависимости для авторизации: `current_user`, `optional_user`, `require_admin`;
- чтение данных пользователя: `get_user`.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.db import UnitOfWork
from app.core.errors import ForbiddenError, UnauthorizedError
from app.modules.identity.models import Role
from app.modules.identity.repository import UserRepository
from app.modules.identity.security import decode_access_token

__all__ = [
    "AuthUser",
    "Role",
    "UserDTO",
    "current_user",
    "get_user",
    "optional_user",
    "require_admin",
]


@dataclass(frozen=True)
class AuthUser:
    """Пользователь текущего запроса — из claims токена, без похода в БД.

    Это важно под нагрузкой: захват места не должен тратить запрос к БД на авторизацию.
    """

    id: uuid.UUID
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN


@dataclass(frozen=True)
class UserDTO:
    id: uuid.UUID
    email: str
    name: str
    role: str


# Токен принимается из httpOnly-cookie (браузер) или заголовка Authorization (k6, Swagger).
_cookie_scheme = APIKeyCookie(name=settings.auth_cookie_name, auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


async def optional_user(
    cookie_token: Annotated[str | None, Depends(_cookie_scheme)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> AuthUser | None:
    token = cookie_token or (bearer.credentials if bearer else None)
    if not token:
        return None
    claims = decode_access_token(token)
    if claims is None:
        return None
    return AuthUser(id=claims.user_id, role=claims.role)


async def current_user(
    user: Annotated[AuthUser | None, Depends(optional_user)],
) -> AuthUser:
    if user is None:
        raise UnauthorizedError()
    return user


async def require_admin(user: Annotated[AuthUser, Depends(current_user)]) -> AuthUser:
    if not user.is_admin:
        raise ForbiddenError()
    return user


async def get_user(uow: UnitOfWork, user_id: uuid.UUID) -> UserDTO | None:
    user = await UserRepository(uow.session).get(user_id)
    if user is None:
        return None
    return UserDTO(id=user.id, email=user.email, name=user.name, role=user.role)
