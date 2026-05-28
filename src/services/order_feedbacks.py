import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import InvariantViolationError, OrderNotFoundError
from src.models.order_feedback_outbox import OrderFeedbackCreatedEvent, OrderFeedbackCreatedEventData
from src.repositories.order_feedbacks import OrderFeedbacksRepository
from src.repositories.orders import OrdersRepository
from src.repositories.order_feedback_outbox import OrderFeedbackOutboxRepository
from src.schemas.feedbacks import FeedbackCreate, FeedbackRead

logger = logging.getLogger(__name__)


class OrderFeedbacksService:
    def __init__(
        self,
        feedbacks_repo: OrderFeedbacksRepository,
        orders_repo: OrdersRepository,
        outbox_repo: OrderFeedbackOutboxRepository,
    ) -> None:
        if feedbacks_repo.db is not orders_repo.db:
            raise InvariantViolationError(
                "OrderFeedbacksRepository must use the same AsyncSession as OrdersRepository"
            )
        if outbox_repo.session is not orders_repo.db:
            raise InvariantViolationError(
                "OrderFeedbackOutboxRepository must use the same AsyncSession as OrdersRepository"
            )
        self.feedbacks_repo = feedbacks_repo
        self.orders_repo = orders_repo
        self.outbox_repo = outbox_repo

    @property
    def db(self) -> AsyncSession:
        return self.orders_repo.db

    async def create_feedback(self, data: FeedbackCreate) -> FeedbackRead:
        order = await self.orders_repo.get_order_with_items(data.order_id)
        if order is None:
            raise OrderNotFoundError(str(data.order_id))

        try:
            feedback = await self.feedbacks_repo.create(data)
            await self.outbox_repo.insert_event(
                event=OrderFeedbackCreatedEvent(
                    event_id=feedback.id,
                    occurred_at=feedback.created_at,
                    data=OrderFeedbackCreatedEventData(
                        feedback_id=feedback.id,
                        order_id=order.id,
                        user_id=order.user_id,
                    ),
                ),
            )
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise

        logger.info(
            "order feedback created feedback_id=%s order_id=%s",
            feedback.id,
            order.id,
        )
        return FeedbackRead.model_validate(feedback)
