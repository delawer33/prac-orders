from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.order_feedback_outbox import OrderFeedbackCreatedEvent, OrderFeedbackCreatedOutboxModel, OrderFeedbackOutboxStatus


class OrderFeedbackOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_event(self, *, event: OrderFeedbackCreatedEvent) -> None:
        row = OrderFeedbackCreatedOutboxModel(
            event_id=event.event_id,
            payload=event.model_dump(mode="json"),
        )
        self.session.add(row)
        await self.session.flush()

    async def get_pending_batch(self, *, limit: int) -> list[OrderFeedbackCreatedOutboxModel]:
        result = await self.session.execute(
            select(OrderFeedbackCreatedOutboxModel)
            .where(OrderFeedbackCreatedOutboxModel.status == OrderFeedbackOutboxStatus.PENDING)
            .order_by(OrderFeedbackCreatedOutboxModel.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def claim_pending_batch(self, *, limit: int) -> list[OrderFeedbackCreatedOutboxModel]:
        result = await self.session.execute(
            select(OrderFeedbackCreatedOutboxModel)
            .where(OrderFeedbackCreatedOutboxModel.status == OrderFeedbackOutboxStatus.PENDING)
            .order_by(OrderFeedbackCreatedOutboxModel.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def mark_published(self, rows: list[OrderFeedbackCreatedOutboxModel]) -> None:
        if not rows:
            return
        ids = [row.id for row in rows]
        published_at = datetime.now(timezone.utc)
        await self.session.execute(
            sa.update(OrderFeedbackCreatedOutboxModel)
            .where(OrderFeedbackCreatedOutboxModel.id.in_(ids))
            .values(status=OrderFeedbackOutboxStatus.PUBLISHED, published_at=published_at)
        )
        await self.session.flush()
        for row in rows:
            row.status = OrderFeedbackOutboxStatus.PUBLISHED
            row.published_at = published_at

