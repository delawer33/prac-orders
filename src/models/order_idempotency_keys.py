from datetime import datetime
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class OrderIdempotencyStatus(StrEnum):
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OrderIdempotencyKeyModel(Base):
    __tablename__ = "order_idempotency_keys"

    key: Mapped[str] = mapped_column(sa.String(255), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[OrderIdempotencyStatus] = mapped_column(
        sa.Enum(OrderIdempotencyStatus, name="order_idempotency_status"),
        nullable=False,
        default=OrderIdempotencyStatus.PROCESSING,
    )
    order_id: Mapped[UUID | None] = mapped_column(sa.Uuid(), nullable=True)
    response_body: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
