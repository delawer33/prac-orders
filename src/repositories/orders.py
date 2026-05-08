import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.exceptions import SagaInvariantError
from src.models.order_items import OrderItemModel
from src.models.orders import OrderModel
from src.schemas.orders import OrderCreate

logger = logging.getLogger(__name__)


class OrdersRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_order_with_items(self, order_id: UUID) -> OrderModel | None:
        result = await self.db.execute(
            select(OrderModel)
            .where(OrderModel.id == order_id)
            .options(selectinload(OrderModel.items))
        )
        return result.scalar_one_or_none()

    async def create_order(self, data: OrderCreate) -> OrderModel:
        if data.user_id is None:
            raise SagaInvariantError("OrderCreate.user_id must be set before persistence")

        order_kwargs = data.model_dump(include={"user_id", "title"})
        order = OrderModel(**order_kwargs)
        self.db.add(order)
        await self.db.flush()

        for item_data in data.items:
            item_kwargs = item_data.model_dump()
            item = OrderItemModel(order_id=order.id, **item_kwargs)
            self.db.add(item)

        await self.db.flush()
        await self.db.refresh(order, ["items"])
        return order
