"""Сага оплаты: успех, отказ банка, сбой, потеря мест после оплаты, идемпотентность,
восстановление после сбоя процесса; заказы и проверка билетов."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import UnitOfWork
from app.modules.orders.payments import FakePaymentGateway, PaymentResult
from app.modules.orders.saga import CheckoutSaga
from tests.test_booking import auth, concert, hold, layout, sync_seatmap

__all__ = ["concert", "layout"]


async def pay(
    client: AsyncClient,
    event_id: str,
    headers: dict[str, str],
    token: str = "tok_ok",
    key: str | None = None,
):
    return await client.post(
        "/api/checkout",
        json={"event_id": event_id, "payment_token": token},
        headers={**headers, "Idempotency-Key": key or uuid.uuid4().hex},
    )


async def scalar(sql: str, **params: Any) -> Any:
    async with UnitOfWork() as uow:
        return await uow.session.scalar(text(sql), params)


async def test_successful_purchase(client: AsyncClient, concert: str, layout: dict) -> None:
    me = auth()
    seats = layout["seats_in"]("V02")[:2]  # VIP-прослойка между ярусами
    for seat_id in seats:
        await hold(client, concert, seat_id, me)
    dance = layout["zone"]("Танцпол")
    await client.post(
        f"/api/events/{concert}/holds/zone",
        json={"section_id": dance["id"], "quantity": 1},
        headers=me,
    )

    resp = await pay(client, concert, me)

    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["state"] == "completed"
    assert result["amount_kopecks"] == 2 * 1_500_000 + 600_000  # 2 × VIP + танцпол
    order = (await client.get(f"/api/orders/{result['order_id']}", headers=me)).json()
    assert order["tickets_count"] == 3
    assert {t["standing"] for t in order["tickets"]} == {True, False}
    assert all(t["code"].startswith("TB1.") for t in order["tickets"])

    # Покупка — одна транзакция: удержания погашены, места проданы, события записаны.
    assert await scalar("SELECT count(*) FROM booking.holds WHERE status = 'converted'") == 3
    assert await scalar("SELECT count(*) FROM booking.sold_seats") == 3
    events = await scalar("SELECT array_agg(event_type ORDER BY id) FROM infra.outbox")
    assert "booking.seats_sold" in events and "orders.order_paid" in events
    await sync_seatmap()
    status = (await client.get(f"/api/events/{concert}/seatmap/status")).json()
    assert set(seats) <= set(status["sold"])
    mine = (await client.get(f"/api/events/{concert}/holds/my", headers=me)).json()
    assert mine["items"] == []


async def test_declined_payment_releases_seats(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    me = auth()
    seat_id = layout["seats_in"]("104")[0]
    await hold(client, concert, seat_id, me)

    resp = await pay(client, concert, me, token="tok_decline")

    assert resp.json()["state"] == "failed"
    assert resp.json()["failure_reason"] == "payment_declined"
    assert resp.json()["order_id"] is None
    # Компенсация: место снова свободно, заказа нет
    assert await scalar("SELECT status FROM booking.holds") == "released"
    assert await scalar("SELECT count(*) FROM orders.orders") == 0
    assert (await hold(client, concert, seat_id, auth())).status_code == 201
    assert (
        await scalar(
            "SELECT count(*) FROM infra.outbox WHERE event_type = 'orders.checkout_failed'"
        )
        == 1
    )


async def test_bank_timeout_fails_saga(client: AsyncClient, concert: str, layout: dict) -> None:
    me = auth()
    await hold(client, concert, layout["seats_in"]("105")[0], me)

    resp = await pay(client, concert, me, token="tok_timeout")

    assert resp.json()["state"] == "failed"
    assert resp.json()["failure_reason"] == "payment_unavailable"
    assert await scalar("SELECT count(*) FROM orders.mock_payments") == 0


async def test_repeated_request_does_not_charge_twice(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    me = auth()
    await hold(client, concert, layout["seats_in"]("106")[0], me)

    first = await pay(client, concert, me, key="same-key-123")
    second = await pay(client, concert, me, key="same-key-123")

    assert first.json()["id"] == second.json()["id"]
    assert second.json()["state"] == "completed"
    assert await scalar("SELECT count(*) FROM orders.mock_payments") == 1
    assert await scalar("SELECT count(*) FROM orders.orders") == 1


class ExpiringGateway(FakePaymentGateway):
    """Банк, пока «думает», удержания пользователя истекают (их погасил уборщик)."""

    async def charge(self, amount_kopecks: int, token: str, idempotency_key: str) -> PaymentResult:
        async with UnitOfWork() as uow:
            await uow.session.execute(
                text("UPDATE booking.holds SET status = 'expired' WHERE status = 'active'")
            )
            await uow.commit()
        return await super().charge(amount_kopecks, token, idempotency_key)


async def test_lost_seats_after_payment_are_refunded(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    user_id = uuid.uuid4()
    from app.modules.identity.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(user_id, 'user')}"}
    await hold(client, concert, layout["seats_in"]("107")[0], headers)
    saga = CheckoutSaga(ExpiringGateway())

    checkout, _ = await saga.start(user_id, uuid.UUID(concert), "tok_ok", "key-lost-seats")
    result = await saga.run(checkout.id)

    assert result.state == "failed"
    assert result.failure_reason == "seats_lost"
    # Деньги списались, но покупка не состоялась — компенсация вернула их
    assert await scalar("SELECT status FROM orders.mock_payments") == "refunded"
    assert await scalar("SELECT count(*) FROM orders.orders") == 0
    assert await scalar("SELECT count(*) FROM booking.sold_seats") == 0


async def test_recover_completes_paid_saga(client: AsyncClient, concert: str, layout: dict) -> None:
    """Процесс упал сразу после списания: банк деньги взял, а заказ не создан."""
    user_id = uuid.uuid4()
    from app.modules.identity.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(user_id, 'user')}"}
    await hold(client, concert, layout["seats_in"]("108")[0], headers)
    gateway = FakePaymentGateway()
    saga = CheckoutSaga(gateway)
    checkout, _ = await saga.start(user_id, uuid.UUID(concert), "tok_ok", "key-crash")
    await gateway.charge(checkout.amount_kopecks, "tok_ok", str(checkout.id))  # и тут «упали»

    result = await saga.recover(checkout.id)

    assert result.state == "completed"
    assert await scalar("SELECT count(*) FROM orders.orders") == 1


async def test_recover_fails_unpaid_saga(client: AsyncClient, concert: str, layout: dict) -> None:
    user_id = uuid.uuid4()
    from app.modules.identity.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(user_id, 'user')}"}
    await hold(client, concert, layout["seats_in"]("109")[0], headers)
    saga = CheckoutSaga(FakePaymentGateway())
    checkout, _ = await saga.start(user_id, uuid.UUID(concert), "tok_ok", "key-no-pay")

    result = await saga.recover(checkout.id)  # банк платежа не видел

    assert result.state == "failed"
    assert result.failure_reason == "payment_not_confirmed"
    assert await scalar("SELECT status FROM booking.holds") == "released"


async def test_nothing_to_pay(client: AsyncClient, concert: str) -> None:
    resp = await pay(client, concert, auth())

    assert resp.status_code == 409
    assert resp.json()["code"] == "NOTHING_TO_PAY"


async def test_idempotency_key_is_required(client: AsyncClient, concert: str) -> None:
    resp = await client.post(
        "/api/checkout", json={"event_id": concert, "payment_token": "tok_ok"}, headers=auth()
    )

    assert resp.status_code == 422


async def test_orders_are_private_and_tickets_verifiable(
    client: AsyncClient, concert: str, layout: dict
) -> None:
    me = auth()
    await hold(client, concert, layout["seats_in"]("110")[0], me)
    order_id = (await pay(client, concert, me)).json()["order_id"]

    mine = (await client.get("/api/me/orders", headers=me)).json()
    assert [o["id"] for o in mine] == [order_id]
    assert mine[0]["event_title"] == "Событие"
    assert (await client.get(f"/api/orders/{order_id}", headers=auth())).status_code == 404

    code = (await client.get(f"/api/orders/{order_id}", headers=me)).json()["tickets"][0]["code"]
    check = (await client.get("/api/tickets/verify", params={"code": code})).json()
    assert check["valid"] and "ряд 1" in check["seat"]
    forged = code[:-2] + ("AA" if not code.endswith("AA") else "BB")
    assert not (await client.get("/api/tickets/verify", params={"code": forged})).json()["valid"]
