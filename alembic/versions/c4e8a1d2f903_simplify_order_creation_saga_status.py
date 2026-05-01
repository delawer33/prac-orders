"""simplify order creation saga status enum and drop last_error

Revision ID: c4e8a1d2f903
Revises: f7c3d9f8a1b2
Create Date: 2026-05-01 10:50:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4e8a1d2f903"
down_revision: Union[str, Sequence[str], None] = "f7c3d9f8a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE order_creation_saga_status RENAME TO order_creation_saga_status_old")
    op.execute(
        """
        CREATE TYPE order_creation_saga_status AS ENUM (
            'started',
            'user_resolved',
            'order_created',
            'compensation_pending',
            'compensated',
            'failed'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE order_creation_sagas
        ALTER COLUMN status TYPE order_creation_saga_status
        USING (
            CASE status::text
                WHEN 'INIT' THEN 'started'::order_creation_saga_status
                WHEN 'USER_CREATE_REQUESTED' THEN 'started'::order_creation_saga_status
                WHEN 'USER_CREATED' THEN 'user_resolved'::order_creation_saga_status
                WHEN 'ORDER_CREATED' THEN 'order_created'::order_creation_saga_status
                WHEN 'COMPENSATION_PENDING' THEN 'compensation_pending'::order_creation_saga_status
                WHEN 'COMPENSATED' THEN 'compensated'::order_creation_saga_status
                WHEN 'FAILED' THEN 'failed'::order_creation_saga_status
                WHEN 'init' THEN 'started'::order_creation_saga_status
                WHEN 'user_create_requested' THEN 'started'::order_creation_saga_status
                WHEN 'user_created' THEN 'user_resolved'::order_creation_saga_status
                WHEN 'order_created' THEN 'order_created'::order_creation_saga_status
                WHEN 'compensation_pending' THEN 'compensation_pending'::order_creation_saga_status
                WHEN 'compensated' THEN 'compensated'::order_creation_saga_status
                WHEN 'failed' THEN 'failed'::order_creation_saga_status
                ELSE 'failed'::order_creation_saga_status
            END
        )
        """
    )
    op.execute("DROP TYPE order_creation_saga_status_old")
    op.drop_column("order_creation_sagas", "last_error")


def downgrade() -> None:
    op.add_column(
        "order_creation_sagas",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.execute("ALTER TYPE order_creation_saga_status RENAME TO order_creation_saga_status_new")
    op.execute(
        """
        CREATE TYPE order_creation_saga_status AS ENUM (
            'INIT',
            'USER_CREATE_REQUESTED',
            'USER_CREATED',
            'ORDER_CREATED',
            'COMPENSATION_PENDING',
            'COMPENSATED',
            'FAILED'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE order_creation_sagas
        ALTER COLUMN status TYPE order_creation_saga_status
        USING (
            CASE status::text
                WHEN 'started' THEN 'USER_CREATE_REQUESTED'::order_creation_saga_status
                WHEN 'user_resolved' THEN 'USER_CREATED'::order_creation_saga_status
                WHEN 'order_created' THEN 'ORDER_CREATED'::order_creation_saga_status
                WHEN 'compensation_pending' THEN 'COMPENSATION_PENDING'::order_creation_saga_status
                WHEN 'compensated' THEN 'COMPENSATED'::order_creation_saga_status
                WHEN 'failed' THEN 'FAILED'::order_creation_saga_status
                ELSE 'FAILED'::order_creation_saga_status
            END
        )
        """
    )
    op.execute("DROP TYPE order_creation_saga_status_new")
