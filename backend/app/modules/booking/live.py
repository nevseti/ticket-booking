"""Схема зала в реальном времени: Server-Sent Events (см. docs/adr/0007).

Воркер, обновив модель чтения, публикует изменение в Redis pub/sub (seatmap_view). Каждый
процесс API держит ОДНО подписочное подключение к Redis на все мероприятия (PSUBSCRIBE) и
раскладывает сообщения по очередям своих зрителей — тысяча открытых схем не превращается
в тысячу подключений к Redis.

Медленный зритель не тормозит остальных: у каждого своя ограниченная очередь. Если она
переполнилась, накопленные изменения выбрасываются и зрителю уходит одно `resync` —
«перечитай снимок». Пачка изменений, скопившихся за время отправки, уходит одной записью.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import structlog
from redis.asyncio import Redis

from app.core.config import settings
from app.core.redis import redis_client
from app.modules.booking.seatmap_view import LIVE_CHANNEL_PREFIX

log = structlog.get_logger()

QUEUE_LIMIT = 256  # изменений в очереди одного зрителя до сброса в resync
BATCH_LIMIT = 64  # сколько изменений склеивать в одну запись
RETRY_MS = 3000  # через сколько браузер переподключится после обрыва


@dataclass(frozen=True)
class Frame:
    kind: str  # delta | resync
    data: str = "{}"

    def encode(self) -> str:
        return f"event: {self.kind}\ndata: {self.data}\n\n"


RESYNC = Frame("resync")


class SeatmapHub:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._subscribers: dict[str, set[asyncio.Queue[Frame]]] = {}
        self._task: asyncio.Task[None] | None = None

    @property
    def viewers(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())

    def subscribe(self, event_id: uuid.UUID) -> asyncio.Queue[Frame]:
        queue: asyncio.Queue[Frame] = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._subscribers.setdefault(str(event_id), set()).add(queue)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._listen())
        return queue

    def unsubscribe(self, event_id: uuid.UUID, queue: asyncio.Queue[Frame]) -> None:
        queues = self._subscribers.get(str(event_id))
        if queues is not None:
            queues.discard(queue)
            if not queues:
                del self._subscribers[str(event_id)]

    def deliver(self, event_id: str, frame: Frame) -> None:
        for queue in self._subscribers.get(event_id, ()):
            try:
                queue.put_nowait(frame)
            except asyncio.QueueFull:
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(RESYNC)

    def _resync_all(self) -> None:
        for event_id in list(self._subscribers):
            self.deliver(event_id, RESYNC)

    async def _listen(self) -> None:
        delay = 1.0
        reconnect = False
        while True:
            try:
                async with self._redis.pubsub() as pubsub:
                    await pubsub.psubscribe(f"{LIVE_CHANNEL_PREFIX}*")
                    if reconnect:
                        # Пока подписки не было, изменения могли пройти мимо.
                        self._resync_all()
                    reconnect, delay = True, 1.0
                    log.info("seatmap_hub_listening")
                    async for message in pubsub.listen():
                        if message["type"] == "pmessage":
                            event_id = message["channel"].removeprefix(LIVE_CHANNEL_PREFIX)
                            self.deliver(event_id, Frame("delta", message["data"]))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("seatmap_hub_disconnected", error=str(exc), retry_in=delay)
                reconnect = True
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task


hub = SeatmapHub(redis_client)


async def sse_stream(event_id: uuid.UUID) -> AsyncIterator[str]:
    """Поток text/event-stream для одного зрителя. Генератор завершается, когда браузер
    закрывает соединение (Starlette отменяет его), и в finally зритель отписывается."""
    queue = hub.subscribe(event_id)
    try:
        yield f"retry: {RETRY_MS}\n\n"
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), settings.sse_heartbeat_seconds)
            except TimeoutError:
                yield ": ping\n\n"  # комментарий SSE: держит соединение через прокси
                continue
            frames = [frame]
            while len(frames) < BATCH_LIMIT and not queue.empty():
                frames.append(queue.get_nowait())
            yield "".join(f.encode() for f in frames)
    finally:
        hub.unsubscribe(event_id, queue)
