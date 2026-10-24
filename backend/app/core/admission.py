"""Сброс нагрузки на входе (admission control).

На одном ядре пропускная способность ограничена: если запросов больше, чем сервер успевает,
очередь растёт, ждут все, и ответы приходят через десятки секунд. Лучше сразу ответить
части клиентов «повторите через пару секунд» (503), а остальных обслужить быстро.

Важно, ГДЕ отказывать. Нагрузочный тест показал: если отказывать по таймауту пула
соединений, 503 прилетает посреди оплаты — деньги списаны, заказ не создан, и сагу
приходится доводить восстановлению. Поэтому отказ — только на входе, до начала работы:
число одновременно выполняемых «тяжёлых» запросов процесса ограничено, а уже начатая
операция (шаги саги) никогда не сбрасывается.
"""

from collections.abc import AsyncIterator

import structlog
from fastapi import Depends

from app.core.errors import ServiceOverloadedError

log = structlog.get_logger()


class Admission:
    """Счётчик одновременно выполняемых запросов одного вида в процессе API.

    Без блокировок: в asyncio проверка и увеличение счётчика выполняются без переключения
    задач, гонки между ними нет.
    """

    def __init__(self, name: str, limit: int) -> None:
        self.name = name
        self.limit = limit
        self.in_flight = 0

    async def admit(self) -> AsyncIterator[None]:
        if self.in_flight >= self.limit:
            log.warning("request_shed", kind=self.name, in_flight=self.in_flight)
            raise ServiceOverloadedError()
        self.in_flight += 1
        try:
            yield
        finally:
            self.in_flight -= 1

    def dependency(self) -> object:
        """Зависимость FastAPI: держит место на всё время обработки запроса."""
        return Depends(self.admit)


# Лимиты на процесс. Приоритет — у тех, кто уже платит: отказ в оплате выбрасывает
# сделанную работу (выбранные места) и ещё 10 минут держит эти места занятыми для других.
# Поэтому нагрузку сбрасывают новые клики по схеме, а лимит оплаты — лишь предохранитель.
# Подобрано нагрузочным тестом на 1 vCPU (docs/loadtest-report.md).
HOLDS = Admission("holds", limit=16)
CHECKOUT = Admission("checkout", limit=40)
