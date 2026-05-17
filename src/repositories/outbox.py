from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.outbox import OrderCreatedOutboxModel, OutboxStatus


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_event(self, *, event_id: UUID, payload: dict) -> None:
        row = OrderCreatedOutboxModel(event_id=event_id, payload=payload)
        self.session.add(row)
        await self.session.flush()

    async def get_pending_batch(self, *, limit: int) -> list[OrderCreatedOutboxModel]:
        result = await self.session.execute(
            select(OrderCreatedOutboxModel)
            .where(OrderCreatedOutboxModel.status == OutboxStatus.PENDING)
            .order_by(OrderCreatedOutboxModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars())

    async def mark_published(self, rows: list[OrderCreatedOutboxModel]) -> None:
        ids = [row.id for row in rows]
        await self.session.execute(
            sa.update(OrderCreatedOutboxModel)
            .where(OrderCreatedOutboxModel.id.in_(ids))
            .values(status=OutboxStatus.PUBLISHED, published_at=datetime.now(timezone.utc))
        )
        await self.session.flush()
