"""Засев данных каталога:

    python -m app.modules.catalog.cli seed-venue   # площадка и схема зала (идемпотентно)
    python -m app.modules.catalog.cli seed-demo    # демо-мероприятия, если их ещё нет

seed-venue выполняется автоматически при каждом деплое (сервис migrate).
"""

import argparse
import asyncio

from app.core.db import UnitOfWork, engine
from app.modules.catalog.seed import seed_demo_events, seed_venue
from app.modules.catalog.service import now_utc


async def _run(command: str) -> str:
    async with UnitOfWork() as uow:
        if command == "seed-venue":
            created = await seed_venue(uow.session)
            result = f"Создана площадка: {created} мест" if created else "Площадка уже существует"
        else:
            created = await seed_demo_events(uow.session, now_utc())
            result = f"Создано мероприятий: {created}" if created else "Мероприятия уже есть"
        await uow.commit()
    await engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(prog="catalog-cli")
    parser.add_argument("command", choices=["seed-venue", "seed-demo"])
    args = parser.parse_args()
    print(asyncio.run(_run(args.command)))


if __name__ == "__main__":
    main()
