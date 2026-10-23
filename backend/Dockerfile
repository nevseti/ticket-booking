# Один образ — три роли (команда задаётся в docker-compose):
#   api      uvicorn app.main:app
#   worker   python -m worker
#   migrate  alembic upgrade head
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

WORKDIR /app

# Сначала только зависимости: слой кэшируется, пока не меняется uv.lock.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY worker ./worker

RUN useradd --system --uid 10001 --no-create-home app
USER app

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000
# Число процессов uvicorn берётся из WEB_CONCURRENCY.
# --timeout-graceful-shutdown: открытые SSE-потоки схемы зала не держат остановку дольше 5 с.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "5"]
