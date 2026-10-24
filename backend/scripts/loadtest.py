"""Подготовка и уборка данных нагрузочного теста (этап 9, каталог loadtest/).

    python -m scripts.loadtest prepare --users 300 --out /loadtest/data.json
    python -m scripts.loadtest prepare --users 50 --prefill 0.6 --out ...   # зал заполнен на 60 %
    python -m scripts.loadtest cleanup

prepare создаёт опубликованный концерт «Нагрузочный тест (k6)» с открытыми продажами и
пользователей loadtest-N@loadtest.invalid, выпускает им токены доступа (k6 ходит с
заголовком Authorization, без входа — вход ограничен 10 попытками в минуту с IP).
--prefill помечает долю сидячих мест проданными (для эксперимента «чтение схемы из Redis
против PostgreSQL»: чем больше занято, тем тяжелее запрос к БД).

cleanup удаляет всё, что связано с тестовым мероприятием и пользователями, во всех модулях.
Это служебный инструмент (как миграции), поэтому он работает SQL-запросами напрямую, мимо
фасадов модулей.
"""

import argparse
import asyncio
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from app.core.db import UnitOfWork, engine
from app.core.redis import redis_client
from app.modules.booking import seatmap_view
from app.modules.catalog.models import Event, EventKind, EventPrice, EventStatus
from app.modules.catalog.reference import get_reference
from app.modules.catalog.venue_layout import HallConfig, SectionKind
from app.modules.identity.security import create_access_token

TITLE = "Нагрузочный тест (k6)"
EMAIL_DOMAIN = "loadtest.invalid"
# Цены концерта в копейках: VIP, фан-зона, танцпол, ярусы
PRICES = {1: 1_200_000, 2: 800_000, 3: 550_000, 4: 650_000, 5: 420_000, 6: 250_000}


async def _event_ids(uow: UnitOfWork) -> list[uuid.UUID]:
    rows = await uow.session.scalars(
        text("SELECT id FROM catalog.events WHERE title = :t"), {"t": TITLE}
    )
    return list(rows)


async def cleanup() -> None:
    async with UnitOfWork() as uow:
        events = await _event_ids(uow)
        users = list(
            await uow.session.scalars(
                text("SELECT id FROM identity.users WHERE email LIKE :p"),
                {"p": f"%@{EMAIL_DOMAIN}"},
            )
        )
        params = {"events": events, "users": users}
        statements = [
            "DELETE FROM orders.mock_payments WHERE idempotency_key IN "
            "(SELECT id::text FROM orders.checkouts WHERE event_id = ANY(:events))",
            "DELETE FROM orders.tickets WHERE event_id = ANY(:events)",
            "DELETE FROM orders.orders WHERE event_id = ANY(:events)",
            "DELETE FROM orders.checkouts WHERE event_id = ANY(:events)",
            "DELETE FROM booking.sold_seats WHERE event_id = ANY(:events)",
            "DELETE FROM booking.holds WHERE event_id = ANY(:events)",
            "DELETE FROM notifications.notifications WHERE user_id = ANY(:users)",
            "DELETE FROM catalog.events WHERE id = ANY(:events)",
            "DELETE FROM identity.users WHERE id = ANY(:users)",
        ]
        for sql in statements:
            await uow.session.execute(text(sql), params)
        await uow.commit()
    for event_id in events:
        await seatmap_view.invalidate(event_id)
    print(f"cleanup: мероприятий {len(events)}, пользователей {len(users)}")


async def prepare(users: int, prefill: float, out: Path) -> None:
    await cleanup()
    now = datetime.now(UTC)
    async with UnitOfWork() as uow:
        event = Event(
            title=TITLE,
            description="Служебное мероприятие нагрузочного теста. Удаляется после прогона.",
            kind=EventKind.CONCERT,
            status=EventStatus.PUBLISHED,
            starts_at=now + timedelta(days=30),
            sales_start_at=now - timedelta(minutes=5),
            sales_end_at=now + timedelta(days=30),
            published_at=now,
            prices=[EventPrice(price_category_id=c, price_kopecks=p) for c, p in PRICES.items()],
        )
        uow.session.add(event)
        await uow.session.flush()
        event_id = event.id

        rows = await uow.session.execute(
            text("""
                INSERT INTO identity.users (email, name, password_hash)
                SELECT 'loadtest-' || n || '@' || :domain, 'Покупатель ' || n, '!'
                FROM generate_series(1, :count) AS n
                RETURNING id
            """),
            {"domain": EMAIL_DOMAIN, "count": users},
        )
        # Хэш '!' не соответствует ни одному паролю: войти этими пользователями нельзя.
        tokens = [create_access_token(user_id, "user") for (user_id,) in rows]

        ref = await get_reference(uow.session)
        seated = [
            s.id
            for s in ref.seats.values()
            if s.section_kind == SectionKind.SEATED and HallConfig.STAGE in s.configs
        ]
        prefilled = random.Random(42).sample(seated, int(len(seated) * prefill))
        if prefilled:
            await uow.session.execute(
                text("""
                    INSERT INTO booking.sold_seats (event_id, seat_id, order_id)
                    SELECT :event_id, seat_id, :order_id
                    FROM unnest(CAST(:seats AS integer[])) AS seat_id
                """),
                {"event_id": event_id, "seats": prefilled, "order_id": uuid.uuid4()},
            )
        await uow.commit()
    await seatmap_view.invalidate(event_id)

    data = json.dumps({"event_id": str(event_id), "tokens": tokens})
    await asyncio.to_thread(out.write_text, data, encoding="utf-8")
    print(
        f"prepare: мероприятие {event_id}, пользователей {users}, "
        f"продано заранее {len(prefilled)} из {len(seated)} сидячих мест → {out}"
    )


async def _main(args: argparse.Namespace) -> None:
    try:
        if args.command == "prepare":
            await prepare(args.users, args.prefill, Path(args.out))
        else:
            await cleanup()
    finally:
        await redis_client.aclose()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="loadtest")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--users", type=int, default=300)
    prep.add_argument("--prefill", type=float, default=0.0, help="доля сидячих мест — продано")
    prep.add_argument("--out", default="loadtest-data.json")
    sub.add_parser("cleanup")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
