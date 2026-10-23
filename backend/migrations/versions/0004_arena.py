"""catalog: ледовая арена с конфигурациями зала, без типа «театр»

Площадка перестроена по образцу ВТБ Арены: два режима зала (hockey / stage), стоячие зоны.
Старая схема удаляется — новую засевает `seed-venue` (выполняется при каждом деплое).
Бронирований на этот момент ещё не существует, поэтому места можно пересоздать.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Типы мероприятий: театра и «другого» на ледовой арене нет — переводим их в шоу.
    op.drop_constraint(op.f("ck_events_kind"), "events", schema="catalog", type_="check")
    op.execute("UPDATE catalog.events SET kind = 'show' WHERE kind IN ('theatre', 'other')")
    op.create_check_constraint(
        op.f("ck_events_kind"), "events", "kind IN ('concert', 'show', 'sport')", schema="catalog"
    )

    # Старая схема площадки больше не нужна. Цены старых категорий не имеют смысла
    # для новой нумерации категорий — их нужно задать заново.
    op.execute("TRUNCATE catalog.seats, catalog.sections, catalog.venues RESTART IDENTITY")
    op.execute("DELETE FROM catalog.event_prices")

    for column in ("rink_x", "rink_y", "rink_width", "rink_height", "rink_radius"):
        op.add_column("venues", sa.Column(column, sa.Float(), nullable=False), schema="catalog")

    op.add_column("sections", sa.Column("kind", sa.String(16), nullable=False), schema="catalog")
    op.add_column(
        "sections",
        sa.Column("configs", postgresql.ARRAY(sa.String(16)), nullable=False),
        schema="catalog",
    )
    op.create_check_constraint(
        op.f("ck_sections_kind"), "sections", "kind IN ('seated', 'standing')", schema="catalog"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_sections_kind"), "sections", schema="catalog", type_="check")
    op.drop_column("sections", "configs", schema="catalog")
    op.drop_column("sections", "kind", schema="catalog")
    for column in ("rink_x", "rink_y", "rink_width", "rink_height", "rink_radius"):
        op.drop_column("venues", column, schema="catalog")
    op.drop_constraint(op.f("ck_events_kind"), "events", schema="catalog", type_="check")
    op.create_check_constraint(
        op.f("ck_events_kind"),
        "events",
        "kind IN ('concert', 'theatre', 'sport', 'show', 'other')",
        schema="catalog",
    )
