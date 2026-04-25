import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.orders import OrderItemModel, OrderModel
from src.schemas.orders import OrderCreate

logger = logging.getLogger(__name__)


async def get_order_with_items(session: AsyncSession, order_id: UUID) -> OrderModel | None:
    result = await session.execute(
        select(OrderModel)
        .where(OrderModel.id == order_id)
        .options(selectinload(OrderModel.items))
    )
    return result.scalar_one_or_none()


async def create_order(session: AsyncSession, data: OrderCreate) -> OrderModel:
    if data.user_id is None:
        raise ValueError("OrderCreate.user_id must be set before persistence")

    order = OrderModel(user_id=data.user_id, title=data.title)
    session.add(order)
    await session.flush()

    for item_data in data.items:
        item = OrderItemModel(
            order_id=order.id,
            product_name=item_data.product_name,
            quantity=item_data.quantity,
            price=item_data.price,
        )
        session.add(item)

    await session.flush()
    await session.refresh(order, ["items"])
    return order
