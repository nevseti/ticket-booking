"""Платёжный шлюз. В MVP — имитация банка: настоящего эквайринга нет (условие задания).

Приложение работает с шлюзом только через интерфейс PaymentGateway, поэтому замена
имитации на настоящего провайдера не затрагивает сагу.

Поведение имитации задаётся «тестовой картой» (токеном), как у реальных провайдеров:

    tok_ok       оплата проходит
    tok_decline  банк отклоняет платёж
    tok_timeout  банк не отвечает (сетевой сбой) — платёж не создан
"""

import asyncio
import random
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.db import SessionFactory
from app.modules.orders.models import MockPayment


class PaymentStatus(StrEnum):
    SUCCEEDED = "succeeded"
    DECLINED = "declined"
    REFUNDED = "refunded"


@dataclass(frozen=True)
class PaymentResult:
    status: PaymentStatus
    payment_ref: str


class PaymentUnavailableError(Exception):
    """Банк не ответил: неизвестно, создан ли платёж (проверяется через get_status)."""


class PaymentGateway(Protocol):
    async def charge(self, amount_kopecks: int, token: str, idempotency_key: str) -> PaymentResult:
        """Списать деньги. Повтор с тем же ключом не создаёт второго платежа."""
        ...

    async def refund(self, payment_ref: str) -> None: ...

    async def get_status(self, idempotency_key: str) -> PaymentResult | None: ...


TEST_TOKENS = ("tok_ok", "tok_decline", "tok_timeout")


class FakePaymentGateway:
    """Банк-имитатор. Свои платежи хранит в отдельной транзакции — как внешний сервис,
    независимо от транзакций приложения."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = SessionFactory):
        self._sessions = session_factory

    async def _latency(self) -> None:
        if settings.fake_payment_latency_ms > 0:
            jitter = random.uniform(0.5, 1.5)
            await asyncio.sleep(settings.fake_payment_latency_ms / 1000 * jitter)

    async def charge(self, amount_kopecks: int, token: str, idempotency_key: str) -> PaymentResult:
        await self._latency()
        if token == "tok_timeout":
            raise PaymentUnavailableError()
        declined = token == "tok_decline" or random.random() < settings.fake_payment_decline_rate
        status = PaymentStatus.DECLINED if declined else PaymentStatus.SUCCEEDED
        async with self._sessions() as session:
            stmt = (
                insert(MockPayment)
                .values(
                    idempotency_key=idempotency_key, amount_kopecks=amount_kopecks, status=status
                )
                .on_conflict_do_nothing(index_elements=[MockPayment.idempotency_key])
            )
            await session.execute(stmt)
            await session.commit()
            payment = await session.scalar(
                select(MockPayment).where(MockPayment.idempotency_key == idempotency_key)
            )
        assert payment is not None
        return PaymentResult(PaymentStatus(payment.status), str(payment.id))

    async def refund(self, payment_ref: str) -> None:
        await self._latency()
        async with self._sessions() as session:
            await session.execute(
                update(MockPayment)
                .where(
                    MockPayment.id == uuid.UUID(payment_ref),
                    MockPayment.status == PaymentStatus.SUCCEEDED,
                )
                .values(status=PaymentStatus.REFUNDED, refunded_at=func.now())
            )
            await session.commit()

    async def get_status(self, idempotency_key: str) -> PaymentResult | None:
        async with self._sessions() as session:
            payment = await session.scalar(
                select(MockPayment).where(MockPayment.idempotency_key == idempotency_key)
            )
        if payment is None:
            return None
        return PaymentResult(PaymentStatus(payment.status), str(payment.id))


def get_gateway() -> PaymentGateway:
    return FakePaymentGateway()
