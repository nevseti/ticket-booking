"""orders

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "checkouts",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="started", nullable=False),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("hold_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payment_token", sa.String(length=50), nullable=False),
        sa.Column("payment_ref", sa.String(length=100), nullable=True),
        sa.Column("failure_reason", sa.String(length=50), nullable=True),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('started', 'paid', 'completed', 'failed')", name=op.f("ck_checkouts_state")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checkouts")),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name=op.f("uq_checkouts_user_id_idempotency_key")
        ),
        schema="orders",
    )
    op.create_table(
        "mock_payments",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('succeeded', 'declined', 'refunded')", name=op.f("ck_mock_payments_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mock_payments")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_mock_payments_idempotency_key")),
        schema="orders",
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("checkout_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="paid", nullable=False),
        sa.Column("total_kopecks", sa.Integer(), nullable=False),
        sa.Column("payment_ref", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('paid')", name=op.f("ck_orders_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("checkout_id", name=op.f("uq_orders_checkout_id")),
        schema="orders",
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"], unique=False, schema="orders")
    op.create_table(
        "tickets",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("seat_id", sa.Integer(), nullable=False),
        sa.Column("section_name", sa.String(length=100), nullable=False),
        sa.Column("row", sa.String(length=8), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("standing", sa.Boolean(), nullable=False),
        sa.Column("category_name", sa.String(length=50), nullable=False),
        sa.Column("price_kopecks", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.orders.id"], name=op.f("fk_tickets_order_id_orders")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("code", name=op.f("uq_tickets_code")),
        sa.UniqueConstraint("event_id", "seat_id", name=op.f("uq_tickets_event_id_seat_id")),
        schema="orders",
    )
    op.create_index(
        op.f("ix_tickets_order_id"), "tickets", ["order_id"], unique=False, schema="orders"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_order_id"), table_name="tickets", schema="orders")
    op.drop_table("tickets", schema="orders")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders", schema="orders")
    op.drop_table("orders", schema="orders")
    op.drop_table("mock_payments", schema="orders")
    op.drop_table("checkouts", schema="orders")
