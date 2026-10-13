from redis.asyncio import Redis

from app.core.config import settings

# Клиент создаётся лениво (соединения открываются при первом запросе) и разделяется
# всеми запросами процесса. Используется для кэша схемы зала и ограничения частоты.
redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
