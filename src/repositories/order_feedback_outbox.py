from datetime import timedelta

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
        subquery = (
            select(OrderFeedbackCreatedOutboxModel.id)
            .where(OrderFeedbackCreatedOutboxModel.status == OrderFeedbackOutboxStatus.PENDING)
            .order_by(OrderFeedbackCreatedOutboxModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        result = await self.session.execute(
            sa.update(OrderFeedbackCreatedOutboxModel)
            .where(OrderFeedbackCreatedOutboxModel.id.in_(subquery))
            .values(status=OrderFeedbackOutboxStatus.PROCESSING, claimed_at=sa.func.now())
            .returning(OrderFeedbackCreatedOutboxModel)
        )
        return list(result.scalars())

    async def reclaim_processing(self, *, timeout_seconds: int) -> None:
        await self.session.execute(
            sa.update(OrderFeedbackCreatedOutboxModel)
            .where(
                OrderFeedbackCreatedOutboxModel.status == OrderFeedbackOutboxStatus.PROCESSING,
                OrderFeedbackCreatedOutboxModel.claimed_at < sa.func.now() - timedelta(seconds=timeout_seconds),
            )
            .values(status=OrderFeedbackOutboxStatus.PENDING, claimed_at=None)
        )

    async def mark_published(self, rows: list[OrderFeedbackCreatedOutboxModel]) -> None:
        if not rows:
            return
        ids = [row.id for row in rows]
        await self.session.execute(
            sa.update(OrderFeedbackCreatedOutboxModel)
            .where(OrderFeedbackCreatedOutboxModel.id.in_(ids))
            .values(status=OrderFeedbackOutboxStatus.PUBLISHED, published_at=sa.func.now())
        )
