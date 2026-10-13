from sqlalchemy.exc import IntegrityError

from app.core.db import UnitOfWork
from app.core.errors import ConflictError, UnauthorizedError
from app.modules.identity.models import Role, User
from app.modules.identity.repository import UserRepository
from app.modules.identity.security import hash_password, verify_password


class EmailTakenError(ConflictError):
    code = "EMAIL_TAKEN"
    title = "Пользователь с таким email уже зарегистрирован"


class InvalidCredentialsError(UnauthorizedError):
    code = "INVALID_CREDENTIALS"
    title = "Неверный email или пароль"


def normalize_email(email: str) -> str:
    return email.strip().lower()


class IdentityService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._users = UserRepository(uow.session)

    async def register(
        self, *, email: str, name: str, password: str, role: Role = Role.USER
    ) -> User:
        email = normalize_email(email)
        if await self._users.get_by_email(email) is not None:
            raise EmailTakenError()
        user = User(email=email, name=name, password_hash=hash_password(password), role=role)
        try:
            await self._users.add(user)
        except IntegrityError as exc:
            # Гонка двух одновременных регистраций на один email: решает уникальный индекс.
            raise EmailTakenError() from exc
        return user

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self._users.get_by_email(normalize_email(email))
        if not verify_password(password, user.password_hash if user else None) or user is None:
            raise InvalidCredentialsError()
        return user
