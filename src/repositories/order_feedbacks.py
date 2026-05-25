from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.order_feedback import OrderFeedbackModel
from src.schemas.feedbacks import FeedbackCreate


class OrderFeedbacksRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: FeedbackCreate) -> OrderFeedbackModel:
        feedback = OrderFeedbackModel(order_id=data.order_id, text=data.text)
        self.db.add(feedback)
        await self.db.flush()
        await self.db.refresh(feedback)
        return feedback

    async def get_by_id(self, feedback_id: UUID) -> OrderFeedbackModel | None:
        return await self.db.get(OrderFeedbackModel, feedback_id)
