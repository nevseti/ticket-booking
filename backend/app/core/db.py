from collections.abc import AsyncIterator
from types import TracebackType
from typing import Self

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Каждый модуль владеет своей схемой PostgreSQL; infra — общая инфраструктура (outbox и т.п.).
MODULE_SCHEMAS: tuple[str, ...] = (
    "identity",
    "catalog",
    "booking",
    "orders",
    "notifications",
    "infra",
)

# Явные имена ограничений: Alembic генерирует стабильные миграции, а ошибки нарушения
# ограничений можно распознавать по имени (например, ux_holds_active).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


class UnitOfWork:
    """Единица работы: одна сессия и одна транзакция.

    Фиксация всегда явная (`await uow.commit()`): так ответ клиенту уходит только после
    успешного COMMIT. Если выйти из контекста без commit — изменения откатываются.
    Фасады модулей принимают UnitOfWork, поэтому операция, затрагивающая несколько
    модулей (например, покупка), выполняется в одной транзакции.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = SessionFactory):
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self.session.rollback()
        finally:
            await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


async def get_uow() -> AsyncIterator[UnitOfWork]:
    """FastAPI-зависимость: UnitOfWork на время запроса."""
    async with UnitOfWork() as uow:
        yield uow
