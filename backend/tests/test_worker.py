"""Фоновый воркер: outbox → брокер, идемпотентные уведомления, уборщик, восстановление саг."""

import asyncio
import json
import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import UnitOfWork
from app.modules.booking import facade as booking
from app.modules.notifications.handlers import handle
from app.modules.notifications.mailer import MemoryMailer
from app.modules.orders import facade as orders
from app.modules.orders.payments import FakePaymentGateway
from app.modules.orders.saga import CheckoutSaga
from app.shared.outbox import add_event
from tests.test_booking import auth, concert, hold, layout
from tests.test_orders import pay
from worker.relay import publish_batch

__all__ = ["concert", "layout"]


class CollectingPublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict, str]] = []

    async def publish(self, routing_key: str, body: bytes, message_id: str) -> None:
        self.messages.append((routing_key, json.loads(body), message_id))


class HandlingPublisher:
    """«Брокер» без брокера: сразу отдаёт сообщение обработчику уведомлений."""

    def __init__(self, mailer: MemoryMailer) -> None:
        self.mailer = mailer

    async def publish(self, routing_key: str, body: bytes, message_id: str) -> None:
        envelope = json.loads(body)
        await handle(routing_key, uuid.UUID(message_id), envelope["payload"], self.mailer)


async def scalar(sql: str, **params):
    async with UnitOfWork() as uow:
        return await uow.session.scalar(text(sql), params)


# --- Outbox ----------------------------------------------------------------------------


async def test_relay_publishes_in_order_once() -> None:
    async with UnitOfWork() as uow:
        for i in range(3):
            add_event(uow.session, "test.happened", i, {"n": i})
        await uow.commit()
    publisher = CollectingPublisher()

    first = await publish_batch(publisher)
    second = await publish_batch(publisher)

    assert (first, second) == (3, 0)
    assert [m[1]["payload"]["n"] for m in publisher.messages] == [0, 1, 2]
    assert {m[0] for m in publisher.messages} == {"test.happened"}
    assert await scalar("SELECT count(*) FROM infra.outbox WHERE published_at IS NULL") == 0


async def test_failed_publish_keeps_event_in_outbox() -> None:
    async with UnitOfWork() as uow:
        add_event(uow.session, "test.happened", 1, {})
        await uow.commit()

    class BrokenPublisher:
        async def publish(self, routing_key: str, body: bytes, message_id: str) -> None:
            raise ConnectionError("брокер недоступен")

    with pytest.raises(ConnectionError):
        await publish_batch(BrokenPublisher())

    # Событие не потеряно: опубликуется, когда брокер вернётся.
    assert await scalar("SELECT count(*) FROM infra.outbox WHERE published_at IS NULL") == 1


# --- Уведомления --------------------------------------------------------------------------


async def test_purchase_sends_tickets_email_exactly_once(
    client: AsyncClient, concert: str, layout: dict, user_headers: dict[str, str]
) -> None:
    for seat_id in layout["seats_in"]("111")[:2]:
        await hold(client, concert, seat_id, user_headers)
    order_id = (await pay(client, concert, user_headers)).json()["order_id"]
    mailer = MemoryMailer()

    await publish_batch(HandlingPublisher(mailer))

    assert len(mailer.sent) == 1
    email = mailer.sent[0]
    assert email["To"] == "user@example.com"
    assert "Ваши билеты" in email["Subject"]
    qr_images = [p for p in email.walk() if p.get_content_type() == "image/png"]
    assert len(qr_images) == 2
    body = email.get_body(("plain",)).get_content()
    assert order_id in body

    # Повторная доставка того же сообщения (at-least-once) не шлёт второе письмо.
    async with UnitOfWork() as uow:
        row = (
            await uow.session.execute(
                text(
                    "SELECT event_id, payload FROM infra.outbox "
                    "WHERE event_type = 'orders.order_paid'"
                )
            )
        ).first()
    handled = await handle("orders.order_paid", row.event_id, row.payload, mailer)
    assert handled is False and len(mailer.sent) == 1

    notes = (await client.get("/api/me/notifications", headers=user_headers)).json()
    assert notes["unread"] == 1
    assert notes["items"][0]["link"] == f"/orders/{order_id}"
    await client.post("/api/me/notifications/read", headers=user_headers)
    assert (await client.get("/api/me/notifications", headers=user_headers)).json()["unread"] == 0


async def test_failed_checkout_creates_notification(
    client: AsyncClient, concert: str, layout: dict, user_headers: dict[str, str]
) -> None:
    await hold(client, concert, layout["seats_in"]("112")[0], user_headers)
    await pay(client, concert, user_headers, token="tok_decline")
    mailer = MemoryMailer()

    await publish_batch(HandlingPublisher(mailer))

    notes = (await client.get("/api/me/notifications", headers=user_headers)).json()
    assert notes["items"][0]["title"] == "Оплата не прошла"
    assert mailer.sent == []


# --- Плановые задачи ----------------------------------------------------------------------


async def test_sweeper_expires_overdue_holds(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    seats = layout["seats_in"]("113")[:3]
    for seat_id in seats:
        await hold(client, concert, seat_id, auth())
    async with UnitOfWork() as uow:
        await uow.session.execute(
            text(
                "UPDATE booking.holds SET expires_at = now() - interval '1 second' "
                "WHERE seat_id = ANY(:s)"
            ),
            {"s": seats[:2]},
        )
        await uow.commit()

    async with UnitOfWork() as uow:
        expired = await booking.expire_overdue_holds(uow)
        await uow.commit()

    assert expired == 2
    assert await scalar("SELECT count(*) FROM booking.holds WHERE status = 'active'") == 1
    payload = await scalar(
        "SELECT payload FROM infra.outbox WHERE event_type = 'booking.holds_expired'"
    )
    assert sorted(payload["seat_ids"]) == sorted(seats[:2])


async def test_recovery_finishes_stuck_checkout(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    user_id = uuid.uuid4()
    from app.modules.identity.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(user_id, 'user')}"}
    await hold(client, concert, layout["seats_in"]("114")[0], headers)
    gateway = FakePaymentGateway()
    checkout, _ = await CheckoutSaga(gateway).start(user_id, uuid.UUID(concert), "tok_ok", "k-1")
    await gateway.charge(checkout.amount_kopecks, "tok_ok", str(checkout.id))  # «упали» здесь
    async with UnitOfWork() as uow:
        await uow.session.execute(
            text("UPDATE orders.checkouts SET updated_at = now() - interval '10 minutes'")
        )
        await uow.commit()

    recovered = await orders.recover_stuck_checkouts(timedelta(minutes=2))

    assert recovered == 1
    assert await scalar("SELECT state FROM orders.checkouts") == "completed"


# --- Настоящий RabbitMQ (локально и в CI; без брокера тест пропускается) -------------------


async def test_rabbitmq_roundtrip() -> None:
    import aio_pika

    from app.core.config import settings
    from worker.rabbit import declare_topology
    from worker.relay import RabbitPublisher

    try:
        connection = await asyncio.wait_for(aio_pika.connect(settings.rabbitmq_url), 3)
    except Exception:
        pytest.skip("RabbitMQ недоступен")
    async with connection:
        await declare_topology(connection)
        channel = await connection.channel(publisher_confirms=True)
        queue = await channel.get_queue("notifications")
        await queue.purge()
        message_id = str(uuid.uuid4())

        await RabbitPublisher(channel).publish(
            "orders.checkout_failed", b'{"payload": {}}', message_id
        )

        message = await queue.get(timeout=5)
        assert message.message_id == message_id
        assert message.routing_key == "orders.checkout_failed"
        await message.ack()
