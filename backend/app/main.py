from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core import health
from app.core.config import settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.core.redis import redis_client
from app.modules.booking import api as booking_api
from app.modules.booking.live import hub as seatmap_hub
from app.modules.catalog import api as catalog_api
from app.modules.identity import api as identity_api
from app.modules.notifications import api as notifications_api
from app.modules.orders import api as orders_api

log = structlog.get_logger()


def operation_id(route: APIRoute) -> str:
    """operationId = имя функции-обработчика: из OpenAPI генерируются хуки useLogin, useMe и т.д."""
    return route.name


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log.info("api_started", version=settings.app_version, env=settings.env)
    yield
    await seatmap_hub.close()
    await redis_client.aclose()
    await engine.dispose()
    log.info("api_stopped")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Ticket Booking API",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        generate_unique_id_function=operation_id,
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(health.router, prefix="/api")
    app.include_router(identity_api.router, prefix="/api")
    app.include_router(catalog_api.router, prefix="/api")
    app.include_router(catalog_api.admin_router, prefix="/api")
    app.include_router(booking_api.router, prefix="/api")
    app.include_router(orders_api.router, prefix="/api")
    app.include_router(notifications_api.router, prefix="/api")
    return app


app = create_app()
