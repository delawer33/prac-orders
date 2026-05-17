"""add order_created_outbox table

Revision ID: 0002_add_order_created_outbox
Revises: 0001_orders_squashed
Create Date: 2026-05-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_order_created_outbox"
down_revision: Union[str, Sequence[str], None] = "0001_orders_squashed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_created_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_order_created_outbox_status", "order_created_outbox", ["status"])


def downgrade() -> None:
    op.drop_index("ix_order_created_outbox_status", table_name="order_created_outbox")
    op.drop_table("order_created_outbox")
