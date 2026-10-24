"""Ограничение частоты запросов: token bucket в Redis (см. docs/adr/0008).

У каждого субъекта (пользователь или IP) по каждому правилу своё «ведро» на `capacity`
жетонов. Запрос забирает жетон, ведро равномерно наполняется: `capacity` жетонов за
`per_seconds`. Значит, можно сделать до `capacity` запросов подряд (всплеск — быстрые клики
по схеме), а дальше — не чаще средней скорости.

Проверка и списание — один Lua-скрипт: атомарно, без гонок между процессами API, а время
берётся у Redis (`TIME`) — часы процессов не должны совпадать.

Если Redis недоступен, запрос пропускается (fail open): ограничитель защищает сервис,
но не должен сам его ронять. Второй рубеж — limit_req в nginx — работает без Redis.
"""

from dataclasses import dataclass

import structlog
from fastapi import Depends, Request
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.errors import RateLimitedError
from app.core.redis import redis_client

log = structlog.get_logger()

# KEYS[1] — ведро; ARGV: ёмкость, скорость пополнения (жетонов в мс).
# Возвращает {разрешено (1/0), осталось жетонов, через сколько мс появится жетон}.
_TOKEN_BUCKET = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)
local bucket = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(bucket[1]) or capacity
local ts = tonumber(bucket[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)
local allowed = 0
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  wait = math.ceil((1 - tokens) / rate)
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', now)
redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / rate))
return {allowed, math.floor(tokens), wait}
"""

_bucket = redis_client.register_script(_TOKEN_BUCKET)


@dataclass(frozen=True)
class Rule:
    name: str
    capacity: int  # сколько запросов подряд можно сделать
    per_seconds: float  # за сколько секунд ведро наполняется целиком

    @property
    def rate_per_ms(self) -> float:
        return self.capacity / (self.per_seconds * 1000)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after: int  # секунд до следующей попытки (0 — можно сейчас)


async def hit(rule: Rule, subject: str) -> Decision:
    """Списать жетон из ведра `subject` по правилу `rule`."""
    if not settings.rate_limit_enabled:
        return Decision(True, rule.capacity, 0)
    try:
        allowed, remaining, wait_ms = await _bucket(
            keys=[f"rl:{rule.name}:{subject}"], args=[rule.capacity, rule.rate_per_ms]
        )
    except RedisError as exc:
        log.warning("rate_limit_unavailable", rule=rule.name, error=str(exc))
        return Decision(True, rule.capacity, 0)
    return Decision(bool(allowed), int(remaining), -(-int(wait_ms) // 1000))


async def enforce(rule: Rule, subject: str) -> None:
    decision = await hit(rule, subject)
    if not decision.allowed:
        log.info("rate_limited", rule=rule.name, subject=subject)
        raise RateLimitedError(retry_after=decision.retry_after)


def client_ip(request: Request) -> str:
    """IP клиента. За nginx его подставляет uvicorn (--proxy-headers) из X-Forwarded-For,
    который nginx перезаписывает адресом соединения — подделать его клиент не может."""
    return request.client.host if request.client else "unknown"


def limit_by_ip(rule: Rule) -> object:
    """Зависимость FastAPI: лимит на IP (вход, регистрация, публичные проверки)."""

    async def dependency(request: Request) -> None:
        await enforce(rule, f"ip:{client_ip(request)}")

    return Depends(dependency)


# Правила. Числа подобраны под живого человека с запасом: быстрые клики по схеме
# проходят, а скрипт, долбящий API, упирается в лимит.
AUTH = Rule("auth", capacity=10, per_seconds=60)  # подбор пароля: 10 попыток в минуту
HOLDS = Rule("holds", capacity=20, per_seconds=10)  # клики по местам: всплеск 20, затем 2/с
CHECKOUT = Rule("checkout", capacity=5, per_seconds=60)  # оплата: 5 попыток в минуту
TICKET_VERIFY = Rule("ticket_verify", capacity=60, per_seconds=60)  # сканер на входе
