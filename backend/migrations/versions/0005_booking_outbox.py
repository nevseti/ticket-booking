"""booking и outbox

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "holds",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("seat_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'converted', 'released', 'expired')", name=op.f("ck_holds_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holds")),
        schema="booking",
    )
    op.create_index(
        "ix_holds_active_expires",
        "holds",
        ["expires_at"],
        unique=False,
        schema="booking",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_holds_active_user",
        "holds",
        ["user_id", "event_id"],
        unique=False,
        schema="booking",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ux_holds_active_seat",
        "holds",
        ["event_id", "seat_id"],
        unique=True,
        schema="booking",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "sold_seats",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("seat_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column(
            "sold_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("event_id", "seat_id", name=op.f("pk_sold_seats")),
        schema="booking",
    )
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
        sa.UniqueConstraint("event_id", name=op.f("uq_outbox_event_id")),
        schema="infra",
    )
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["id"],
        unique=False,
        schema="infra",
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_unpublished",
        table_name="outbox",
        schema="infra",
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.drop_table("outbox", schema="infra")
    op.drop_table("sold_seats", schema="booking")
    op.drop_index(
        "ux_holds_active_seat",
        table_name="holds",
        schema="booking",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index(
        "ix_holds_active_user",
        table_name="holds",
        schema="booking",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index(
        "ix_holds_active_expires",
        table_name="holds",
        schema="booking",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_table("holds", schema="booking")
