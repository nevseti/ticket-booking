"""Фоновый воркер: `python -m worker`. Тот же образ, что и у API, другая точка входа.

Задачи (асинхронно, в одном процессе):
    relay       публикует события outbox в RabbitMQ
    consumer    обрабатывает очередь уведомлений (письма, уведомления в приложении)
    projector   обновляет модель чтения схемы зала в Redis (CQRS) по событиям booking.*
    sweeper     гасит просроченные удержания мест (раз в 15 с)
    recovery    доводит до конца «зависшие» саги оплаты (раз в минуту)
"""

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable
from datetime import timedelta

import structlog

from app.core.config import settings
from app.core.db import UnitOfWork, engine
from app.core.logging import configure_logging
from app.modules.booking import facade as booking
from app.modules.notifications.mailer import SmtpMailer
from app.modules.orders import facade as orders
from worker.consumer import consume_notifications, consume_projection
from worker.rabbit import connect, declare_topology
from worker.relay import RabbitPublisher, publish_batch

log = structlog.get_logger()

# Пауза, когда событий нет. Задаёт задержку обновления схемы зала у зрителей.
RELAY_IDLE_SECONDS = 0.25


async def relay_loop(stop: asyncio.Event, publisher: RabbitPublisher) -> None:
    while not stop.is_set():
        try:
            published = await publish_batch(publisher)
            if published:
                log.info("outbox_published", count=published)
                continue  # есть ещё — сразу следующая пачка
        except Exception:
            log.exception("outbox_relay_failed")
        await _sleep(stop, RELAY_IDLE_SECONDS)


async def periodic(
    stop: asyncio.Event, name: str, interval: int, job: Callable[[], Awaitable[int]]
) -> None:
    while not stop.is_set():
        try:
            done = await job()
            if done:
                log.info(f"{name}_done", count=done)
        except Exception:
            log.exception(f"{name}_failed")
        await _sleep(stop, interval)


async def sweep_holds() -> int:
    async with UnitOfWork() as uow:
        expired = await booking.expire_overdue_holds(uow)
        await uow.commit()
    return expired


async def recover_sagas() -> int:
    return await orders.recover_stuck_checkouts(
        timedelta(seconds=settings.saga_stuck_after_seconds)
    )


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def main() -> None:
    configure_logging()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # На Windows обработчики сигналов недоступны — там остановка через KeyboardInterrupt.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    log.info("worker_starting", version=settings.app_version, env=settings.env)
    connection = await connect()
    await declare_topology(connection)
    publish_channel = await connection.channel(publisher_confirms=True)
    await consume_notifications(connection, SmtpMailer())
    await consume_projection(connection, "seatmap", booking.project_seatmap_event)

    tasks = [
        asyncio.create_task(relay_loop(stop, RabbitPublisher(publish_channel))),
        asyncio.create_task(
            periodic(stop, "hold_sweep", settings.hold_sweep_interval_seconds, sweep_holds)
        ),
        asyncio.create_task(
            periodic(stop, "saga_recovery", settings.saga_recovery_interval_seconds, recover_sagas)
        ),
    ]
    log.info("worker_started")
    await stop.wait()
    log.info("worker_stopping")
    await asyncio.gather(*tasks, return_exceptions=True)
    await connection.close()
    await engine.dispose()
    log.info("worker_stopped")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
