"""Администрирование пользователей из командной строки.

    python -m app.modules.identity.cli create-admin --email admin@example.com --name Админ

Пароль спрашивается интерактивно (или берётся из переменной ADMIN_PASSWORD).
На сервере: docker compose exec api python -m app.modules.identity.cli create-admin ...
"""

import argparse
import asyncio
import getpass
import os

from sqlalchemy import update

from app.core.db import UnitOfWork, engine
from app.modules.identity.models import Role, User
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import IdentityService, normalize_email


async def create_admin(email: str, name: str, password: str) -> str:
    async with UnitOfWork() as uow:
        existing = await UserRepository(uow.session).get_by_email(normalize_email(email))
        if existing is not None:
            await uow.session.execute(
                update(User).where(User.id == existing.id).values(role=Role.ADMIN)
            )
            result = f"Пользователь {existing.email} повышен до администратора"
        else:
            user = await IdentityService(uow).register(
                email=email, name=name, password=password, role=Role.ADMIN
            )
            result = f"Создан администратор {user.email}"
        await uow.commit()
    await engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(prog="identity-cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="создать администратора или повысить существующего")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Администратор")
    args = parser.parse_args()

    if args.command == "create-admin":
        password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Пароль: ")
        if len(password) < 8:
            parser.error("пароль должен быть не короче 8 символов")
        print(asyncio.run(create_admin(args.email, args.name, password)))


if __name__ == "__main__":
    main()
