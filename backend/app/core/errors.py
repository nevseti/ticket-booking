"""Ошибки приложения и их отображение в формат Problem Details (RFC 9457)."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()

PROBLEM_JSON = "application/problem+json"


class Problem(BaseModel):
    """Тело ошибки (RFC 9457). `code` — машинный код для клиента."""

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str | None = None
    instance: str | None = None


_STATUS_DESCRIPTIONS = {
    401: "Требуется вход",
    403: "Недостаточно прав",
    404: "Не найдено",
    409: "Конфликт",
    422: "Ошибка валидации",
    429: "Слишком много запросов",
    503: "Сервис перегружен",
}


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """Описание ошибок для OpenAPI: `APIRouter(responses=problem_responses(401, 422))`."""
    return {
        status: {
            "model": Problem,
            "description": _STATUS_DESCRIPTIONS.get(status, "Ошибка"),
            "content": {PROBLEM_JSON: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        }
        for status in statuses
    }


class AppError(Exception):
    """Базовая ошибка предметной области.

    `code` — машинный код для фронтенда (например, SEAT_UNAVAILABLE),
    `detail` — человекочитаемое пояснение.
    """

    status_code: int = 400
    code: str = "BAD_REQUEST"
    title: str = "Некорректный запрос"
    headers: dict[str, str] | None = None  # дополнительные заголовки ответа

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        if code is not None:
            self.code = code
        self.extra = extra or {}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    title = "Не найдено"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    title = "Конфликт"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    title = "Требуется вход"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    title = "Недостаточно прав"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    title = "Слишком много запросов"

    def __init__(self, retry_after: int = 1) -> None:
        retry_after = max(1, retry_after)
        super().__init__(
            f"Слишком много запросов подряд. Повторите через {retry_after} с.",
            extra={"retry_after": retry_after},
        )
        self.headers = {"Retry-After": str(retry_after)}


class ServiceOverloadedError(AppError):
    status_code = 503
    code = "SERVICE_OVERLOADED"
    title = "Сервис перегружен"
    headers = {"Retry-After": "2"}  # noqa: RUF012 — заголовок одинаков для всех экземпляров

    def __init__(self) -> None:
        super().__init__(
            "Сейчас очень много покупателей. Повторите через пару секунд.",
            extra={"retry_after": 2},
        )


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
        "instance": request.url.path,
    }
    if detail:
        body["detail"] = detail
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem_response(
            request,
            status=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            extra=exc.extra,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return problem_response(
            request,
            status=422,
            code="VALIDATION_ERROR",
            title="Ошибка валидации",
            extra={"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(
            request,
            status=exc.status_code,
            code="HTTP_ERROR",
            title=str(exc.detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(PoolTimeoutError)
    async def handle_pool_timeout(request: Request, exc: PoolTimeoutError) -> JSONResponse:
        # Страховка: обычно нагрузку сбрасывает admission control на входе (core/admission).
        # Если всё же все соединения с БД заняты дольше db_pool_timeout — 503, а не 500.
        log.warning("db_pool_exhausted", path=request.url.path)
        error = ServiceOverloadedError()
        return problem_response(
            request,
            status=error.status_code,
            code=error.code,
            title=error.title,
            detail=error.detail,
            extra=error.extra,
            headers=error.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path)
        return problem_response(
            request, status=500, code="INTERNAL_ERROR", title="Внутренняя ошибка сервера"
        )
