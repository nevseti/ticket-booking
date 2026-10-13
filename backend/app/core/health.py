from typing import Literal

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.redis import redis_client

router = APIRouter(tags=["system"])
log = structlog.get_logger()


class HealthOut(BaseModel):
    status: Literal["ok"]
    version: str
    env: str


class ReadyOut(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Живость процесса: ответ без обращения к зависимостям."""
    return HealthOut(status="ok", version=settings.app_version, env=settings.env)


@router.get("/ready", response_model=ReadyOut, responses={503: {"model": ReadyOut}})
async def ready() -> JSONResponse:
    """Готовность: доступны ли PostgreSQL и Redis."""
    checks = {"postgres": False, "redis": False}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception as exc:
        log.warning("ready_check_failed", dependency="postgres", error=str(exc))
    try:
        checks["redis"] = bool(await redis_client.ping())
    except Exception as exc:
        log.warning("ready_check_failed", dependency="redis", error=str(exc))

    ok = all(checks.values())
    body = ReadyOut(status="ok" if ok else "degraded", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)
