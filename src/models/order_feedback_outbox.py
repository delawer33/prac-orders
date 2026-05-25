from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class OrderFeedbackCreatedEventData(BaseModel):
    feedback_id: UUID
    order_id: UUID
    user_id: UUID


class OrderFeedbackCreatedEvent(BaseModel):
    event_id: UUID
    event_type: Literal["OrderFeedbackCreated"] = "OrderFeedbackCreated"
    occurred_at: datetime
    data: OrderFeedbackCreatedEventData

    def partition_key(self) -> bytes:
        return str(self.data.user_id).encode("utf-8")


class OrderFeedbackOutboxStatus:
    PENDING = "pending"
    PUBLISHED = "published"


class OrderFeedbackCreatedOutboxModel(Base):
    __tablename__ = "order_feedback_outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(sa.Uuid(), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(sa.JSON(), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default=OrderFeedbackOutboxStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
