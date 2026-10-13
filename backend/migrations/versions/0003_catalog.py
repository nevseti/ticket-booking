"""catalog: площадка, мероприятия, цены

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sales_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sales_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("poster_url", sa.String(length=500), nullable=True),
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
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('concert', 'theatre', 'sport', 'show', 'other')", name=op.f("ck_events_kind")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'cancelled')", name=op.f("ck_events_status")
        ),
        sa.CheckConstraint("sales_end_at <= starts_at", name=op.f("ck_events_sales_before_start")),
        sa.CheckConstraint("sales_start_at < sales_end_at", name=op.f("ck_events_sales_window")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        schema="catalog",
    )
    op.create_index(
        "ix_events_status_starts_at",
        "events",
        ["status", "starts_at"],
        unique=False,
        schema="catalog",
    )
    op.create_table(
        "price_categories",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_categories")),
        schema="catalog",
    )
    op.create_table(
        "venues",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("stage_path", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_venues")),
        schema="catalog",
    )
    op.create_table(
        "event_prices",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("price_category_id", sa.SmallInteger(), nullable=False),
        sa.Column("price_kopecks", sa.Integer(), nullable=False),
        sa.CheckConstraint("price_kopecks > 0", name=op.f("ck_event_prices_positive")),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["catalog.events.id"],
            name=op.f("fk_event_prices_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["price_category_id"],
            ["catalog.price_categories.id"],
            name=op.f("fk_event_prices_price_category_id_price_categories"),
        ),
        sa.PrimaryKeyConstraint("event_id", "price_category_id", name=op.f("pk_event_prices")),
        schema="catalog",
    )
    op.create_table(
        "sections",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("venue_id", sa.SmallInteger(), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("label_x", sa.Float(), nullable=False),
        sa.Column("label_y", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["catalog.venues.id"], name=op.f("fk_sections_venue_id_venues")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sections")),
        sa.UniqueConstraint("code", name=op.f("uq_sections_code")),
        schema="catalog",
    )
    op.create_table(
        "seats",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("section_id", sa.SmallInteger(), nullable=False),
        sa.Column("row", sa.String(length=8), nullable=False),
        sa.Column("number", sa.SmallInteger(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("price_category_id", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["price_category_id"],
            ["catalog.price_categories.id"],
            name=op.f("fk_seats_price_category_id_price_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["section_id"], ["catalog.sections.id"], name=op.f("fk_seats_section_id_sections")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seats")),
        sa.UniqueConstraint(
            "section_id", "row", "number", name=op.f("uq_seats_section_id_row_number")
        ),
        schema="catalog",
    )
    op.create_index(
        op.f("ix_seats_section_id"), "seats", ["section_id"], unique=False, schema="catalog"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_seats_section_id"), table_name="seats", schema="catalog")
    op.drop_table("seats", schema="catalog")
    op.drop_table("sections", schema="catalog")
    op.drop_table("event_prices", schema="catalog")
    op.drop_table("venues", schema="catalog")
    op.drop_table("price_categories", schema="catalog")
    op.drop_index("ix_events_status_starts_at", table_name="events", schema="catalog")
    op.drop_table("events", schema="catalog")
