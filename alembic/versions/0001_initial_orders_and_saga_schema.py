"""initial orders and saga schema

Revision ID: 0001_orders_squashed
Revises:
Create Date: 2026-05-01 13:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_orders_squashed"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "order_creation_sagas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("resolved_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_user_created", sa.Boolean(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "started",
                "user_resolved",
                "order_created",
                "compensation_pending",
                "compensated",
                "failed",
                name="order_creation_saga_status",
            ),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_creation_sagas_idempotency_key",
        "order_creation_sagas",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_order_creation_sagas_request_fingerprint",
        "order_creation_sagas",
        ["request_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_order_creation_sagas_request_fingerprint", table_name="order_creation_sagas")
    op.drop_index("ix_order_creation_sagas_idempotency_key", table_name="order_creation_sagas")
    op.drop_table("order_creation_sagas")
    op.drop_table("order_items")
    op.drop_table("orders")
