from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class OutboxStatus:
    PENDING = "pending"
    PUBLISHED = "published"


class OrderCreatedOutboxModel(Base):
    __tablename__ = "order_created_outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(sa.Uuid(), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(sa.JSON(), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default=OutboxStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
