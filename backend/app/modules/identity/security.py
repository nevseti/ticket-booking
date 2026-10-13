"""Хеширование паролей и токены доступа."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

_hasher = PasswordHash.recommended()  # Argon2id с рекомендуемыми параметрами

# Хеш для сравнения, когда пользователь не найден: вход по несуществующему email
# занимает столько же времени, сколько по существующему (нет утечки через тайминг).
_DUMMY_HASH = _hasher.hash("timing-attack-protection")

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: str


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenClaims | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "role"]},
        )
        return TokenClaims(user_id=uuid.UUID(payload["sub"]), role=payload["role"])
    except (jwt.PyJWTError, ValueError):
        return None
