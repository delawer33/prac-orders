"""add replay fields to order creation saga

Revision ID: f7c3d9f8a1b2
Revises: 8b3a9a15fb54
Create Date: 2026-04-29 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7c3d9f8a1b2"
down_revision: Union[str, Sequence[str], None] = "8b3a9a15fb54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("order_creation_sagas", sa.Column("response_body", sa.JSON(), nullable=True))
    op.add_column("order_creation_sagas", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("order_creation_sagas", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("order_creation_sagas", "error_message")
    op.drop_column("order_creation_sagas", "error_code")
    op.drop_column("order_creation_sagas", "response_body")
