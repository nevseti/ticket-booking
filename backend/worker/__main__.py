"""Фоновый воркер: `python -m worker`.

Тот же образ, что и у API, другая точка входа. Сейчас — каркас с корректной
остановкой; публикатор outbox, обработчики RabbitMQ и таймеры появятся на этапе 6.
"""

import asyncio
import contextlib
import signal

import structlog

from app.core.config import settings
from app.core.logging import configure_logging

log = structlog.get_logger()

HEARTBEAT_SECONDS = 60


async def main() -> None:
    configure_logging()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # На Windows обработчики сигналов недоступны — там остановка через KeyboardInterrupt.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    log.info("worker_started", version=settings.app_version, env=settings.env)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
        except TimeoutError:
            log.info("worker_heartbeat")
    log.info("worker_stopped")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
