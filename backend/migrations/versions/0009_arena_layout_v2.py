"""catalog: версия схемы зала и ложи (схема v2 — VIP/лаунж-кольцо, ложи, ровные ряды)

Сами места не трогаем: схему перестраивает `seed-venue` (он выполняется при каждом деплое
после миграций). Увидев layout_version = 1, он строит новую схему и переносит на неё уже
проданные места и билеты — см. catalog/seed.py.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venues",
        sa.Column("layout_version", sa.SmallInteger(), server_default="1", nullable=False),
        schema="catalog",
    )
    op.add_column(
        "venues",
        sa.Column("boxes", postgresql.JSONB(), server_default="[]", nullable=False),
        schema="catalog",
    )


def downgrade() -> None:
    op.drop_column("venues", "boxes", schema="catalog")
    op.drop_column("venues", "layout_version", schema="catalog")
