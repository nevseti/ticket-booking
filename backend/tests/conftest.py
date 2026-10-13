import os

# Настройки читаются при импорте app.*, поэтому окружение задаём до импортов приложения.
os.environ["ENV"] = "test"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://tickets:tickets@localhost:5433/tickets_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import asyncio  # noqa: E402
from collections.abc import AsyncIterator, Callable, Coroutine  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import make_url, text  # noqa: E402

from app.core.db import MODULE_SCHEMAS, engine  # noqa: E402
from app.db_models import Base  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_in_thread(fn: Callable[[], Any]) -> Any:
    """Синхронно выполнить код, который сам вызывает asyncio.run (Alembic, служебные запросы),
    не задевая цикл событий pytest-asyncio."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(fn).result()


def _admin_dsn(url: str) -> tuple[str, str]:
    parsed = make_url(url)
    admin = parsed.set(drivername="postgresql", database="postgres")
    return admin.render_as_string(hide_password=False), parsed.database or ""


async def _recreate_test_database() -> None:
    admin_dsn, db_name = _admin_dsn(TEST_DATABASE_URL)
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()

    db_dsn = make_url(TEST_DATABASE_URL).set(drivername="postgresql")
    conn = await asyncpg.connect(db_dsn.render_as_string(hide_password=False))
    try:
        for schema in MODULE_SCHEMAS:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await conn.execute("DROP TABLE IF EXISTS public.alembic_version")
    finally:
        await conn.close()


def _run(coro_fn: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
    return _run_in_thread(lambda: asyncio.run(coro_fn()))


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    """Чистая тестовая БД с применёнными миграциями — один раз на прогон."""
    _run(_recreate_test_database)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    _run_in_thread(lambda: command.upgrade(cfg, "head"))


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    """Перед каждым тестом — пустые таблицы (структура остаётся)."""
    tables = [f'{t.schema}."{t.name}"' for t in Base.metadata.sorted_tables]
    if tables:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
