"""poster credit

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events", sa.Column("poster_credit", sa.String(length=300), nullable=True), schema="catalog"
    )
    op.add_column(
        "events", sa.Column("poster_source", sa.String(length=500), nullable=True), schema="catalog"
    )


def downgrade() -> None:
    op.drop_column("events", "poster_source", schema="catalog")
    op.drop_column("events", "poster_credit", schema="catalog")
