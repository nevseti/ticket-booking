"""Модель чтения схемы зала в Redis (CQRS).

Запись — захват, освобождение и продажа мест — идёт в PostgreSQL: там гарантии от двойной
продажи. Занятость зала читают гораздо чаще (каждый открытый экран схемы), поэтому она
читается из проекции в Redis, которую фоновый воркер обновляет по событиям booking.*.

Проекция мероприятия — один HASH `seatmap:{event_id}`. Один ключ, а не несколько: при
нехватке памяти Redis (allkeys-lru) вытесняет проекцию целиком, и она пересобирается из БД,
а не остаётся наполовину пустой.

    v        версия: +1 на каждое изменение; по ней клиент замечает пропущенные изменения
    s{seat}  сидячее место: h — удержано, s — продано (свободные места не хранятся)
    p{seat}  место стоячей зоны (h/s) — чтобы повтор события не сдвинул счётчик дважды
    z{zone}  сколько мест стоячей зоны занято

Каждое изменение публикуется в канал `seatmap-live:{event_id}` (Redis pub/sub) — его
слушают SSE-подключения (live.py).

Согласованность. События приходят по порядку и «хотя бы один раз»; применение идемпотентно
(удержать уже удержанное, освободить свободное — ничего не меняет), поэтому повторы не
портят проекцию. Если проекции нет (ещё не строилась, вытеснена, истекла), её строят из
PostgreSQL: API — при чтении, воркер — при событии. Строит тот, кто успел первым (Lua с
проверкой EXISTS); событие после этого всё равно применяется поверх — повтор безвреден.
"""

import time
import uuid
from typing import Any

import structlog
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.db import UnitOfWork
from app.core.redis import redis_client
from app.modules.booking.repository import HoldRepository
from app.modules.booking.schemas import SeatmapStatus, ZoneAvailability
from app.modules.booking.service import HOLDS_EXPIRED, SEATS_HELD, SEATS_RELEASED, SEATS_SOLD
from app.modules.catalog import facade as catalog

log = structlog.get_logger()

LIVE_CHANNEL_PREFIX = "seatmap-live:"

# Тип события → операция над проекцией
OPERATIONS = {
    SEATS_HELD: "hold",
    SEATS_RELEASED: "release",
    HOLDS_EXPIRED: "release",
    SEATS_SOLD: "sell",
}

# KEYS[1] — проекция; ARGV: операция, TTL, канал, затем пары (место, зона; 0 — сидячее).
# Возвращает новую версию, -1 — проекции нет (её нужно построить).
_APPLY = """
if redis.call('EXISTS', KEYS[1]) == 0 then return -1 end
local op = ARGV[1]
local seats, zones = {}, {}
local changed = false
for i = 4, #ARGV, 2 do
  local seat, zone = ARGV[i], tonumber(ARGV[i + 1])
  local field = (zone > 0 and 'p' or 's') .. seat
  local cur = redis.call('HGET', KEYS[1], field)
  local new = cur
  if op == 'hold' then
    if not cur then new = 'h' end
  elseif op == 'release' then
    if cur == 'h' then new = false end
  else
    new = 's'
  end
  if new ~= cur then
    changed = true
    if new then redis.call('HSET', KEYS[1], field, new) else redis.call('HDEL', KEYS[1], field) end
    if zone == 0 then
      seats[seat] = new or 'f'
    elseif not cur ~= not new then
      zones[tostring(zone)] = redis.call('HINCRBY', KEYS[1], 'z' .. zone, new and 1 or -1)
    end
  end
end
if not changed then return tonumber(redis.call('HGET', KEYS[1], 'v')) end
local v = redis.call('HINCRBY', KEYS[1], 'v', 1)
redis.call('EXPIRE', KEYS[1], ARGV[2])
redis.call('PUBLISH', ARGV[3], cjson.encode({v = v, seats = seats, zones = zones}))
return v
"""

# KEYS[1] — проекция; ARGV: TTL, начальная версия, затем пары (поле, значение).
# Строит проекцию, только если её ещё нет: 1 — построена, 0 — уже кто-то построил.
_BUILD = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
redis.call('HSET', KEYS[1], 'v', ARGV[2])
for i = 3, #ARGV, 2 do redis.call('HSET', KEYS[1], ARGV[i], ARGV[i + 1]) end
redis.call('EXPIRE', KEYS[1], ARGV[1])
return 1
"""

_apply = redis_client.register_script(_APPLY)
_build = redis_client.register_script(_BUILD)


def projection_key(event_id: uuid.UUID) -> str:
    return f"seatmap:{event_id}"


def live_channel(event_id: uuid.UUID) -> str:
    return f"{LIVE_CHANNEL_PREFIX}{event_id}"


async def _state_from_db(uow: UnitOfWork, event_id: uuid.UUID) -> dict[str, str]:
    """Поля проекции, посчитанные по PostgreSQL (без версии)."""
    held, sold = await HoldRepository(uow.session).taken_seats(event_id)
    zones = await catalog.standing_zones(uow)
    fields: dict[str, str] = {}
    taken: dict[int, int] = {}
    for seat_id, state in [*((s, "h") for s in held), *((s, "s") for s in sold)]:
        zone = zones.zone_of.get(seat_id)
        field = f"p{seat_id}" if zone else f"s{seat_id}"
        if zone and field not in fields:
            taken[zone] = taken.get(zone, 0) + 1
        fields[field] = state  # проданное перекрывает удержанное
    fields.update({f"z{zone}": str(count) for zone, count in taken.items()})
    return fields


async def build(uow: UnitOfWork, event_id: uuid.UUID) -> bool:
    """Построить проекцию по PostgreSQL, если её нет. Версия начинается с текущего времени
    в миллисекундах: так версии новой проекции не совпадут с версиями вытесненной."""
    fields = await _state_from_db(uow, event_id)
    args: list[Any] = [settings.seatmap_cache_ttl_seconds, int(time.time() * 1000)]
    for field, value in fields.items():
        args += [field, value]
    built = await _build(keys=[projection_key(event_id)], args=args)
    if built:
        log.info("seatmap_projection_built", event_id=str(event_id), fields=len(fields))
    return bool(built)


async def project(uow: UnitOfWork, event_type: str, payload: dict[str, Any]) -> int | None:
    """Применить событие booking.* к проекции. Возвращает новую версию (None — событие не
    про занятость мест)."""
    operation = OPERATIONS.get(event_type)
    if operation is None:
        return None
    event_id = uuid.UUID(payload["event_id"])
    zones = await catalog.standing_zones(uow)
    args: list[Any] = [operation, settings.seatmap_cache_ttl_seconds, live_channel(event_id)]
    for seat_id in payload["seat_ids"]:
        args += [seat_id, zones.zone_of.get(seat_id, 0)]
    keys = [projection_key(event_id)]
    version = await _apply(keys=keys, args=args)
    if version == -1:
        # Событие уже зафиксировано в БД, поэтому построенная проекция его учитывает;
        # повторное применение ниже ничего не изменит, если нас не опередили.
        await build(uow, event_id)
        version = await _apply(keys=keys, args=args)
    return int(version)


async def invalidate(event_id: uuid.UUID) -> None:
    """Сбросить проекцию: следующее чтение построит её заново из БД."""
    await redis_client.delete(projection_key(event_id))


def _parse(raw: dict[str, str], capacity: dict[int, int]) -> SeatmapStatus:
    held: list[int] = []
    sold: list[int] = []
    taken: dict[int, int] = {}
    for field, value in raw.items():
        kind = field[0]
        if kind == "s":
            (held if value == "h" else sold).append(int(field[1:]))
        elif kind == "z":
            taken[int(field[1:])] = int(value)
    return SeatmapStatus(
        version=int(raw["v"]),
        held=sorted(held),
        sold=sorted(sold),
        zones=[
            ZoneAvailability(section_id=zone, capacity=cap, available=cap - taken.get(zone, 0))
            for zone, cap in capacity.items()
        ],
    )


async def status_from_db(uow: UnitOfWork, event_id: uuid.UUID) -> SeatmapStatus:
    """Занятость напрямую из PostgreSQL. Версия 0 — «без версии»: клиент на каждое
    изменение просто перечитывает схему."""
    zones = await catalog.standing_zones(uow)
    raw = await _state_from_db(uow, event_id)
    return _parse({**raw, "v": "0"}, zones.capacity)


async def read_status(uow: UnitOfWork, event_id: uuid.UUID) -> SeatmapStatus:
    """Занятость зала из модели чтения; при её отсутствии — построить из БД.
    Если Redis недоступен — читаем из PostgreSQL: сайт работает, просто медленнее."""
    if settings.seatmap_read_model == "db":
        return await status_from_db(uow, event_id)
    zones = await catalog.standing_zones(uow)
    key = projection_key(event_id)
    try:
        raw = await redis_client.hgetall(key)
        if not raw:
            await build(uow, event_id)
            raw = await redis_client.hgetall(key)
        if raw:
            return _parse(raw, zones.capacity)
    except RedisError as exc:
        log.warning("seatmap_read_model_unavailable", error=str(exc))
    return await status_from_db(uow, event_id)
