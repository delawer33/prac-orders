from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class OrderCreationSagaStatus(StrEnum):
    STARTED = "started"
    USER_RESOLVED = "user_resolved"
    ORDER_CREATED = "order_created"
    COMPENSATION_PENDING = "compensation_pending"
    COMPENSATED = "compensated"
    FAILED = "failed"


class OrderCreationSagaModel(Base):
    __tablename__ = "order_creation_sagas"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True, index=True)
    request_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(sa.String(320), nullable=True)
    resolved_user_id: Mapped[UUID | None] = mapped_column(sa.Uuid(), nullable=True)
    resolved_user_created: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    status: Mapped[OrderCreationSagaStatus] = mapped_column(
        sa.Enum(
            OrderCreationSagaStatus,
            name="order_creation_saga_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=OrderCreationSagaStatus.STARTED,
    )
    order_id: Mapped[UUID | None] = mapped_column(sa.Uuid(), nullable=True)
    response_body: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    retry_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
