import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients import users_client
from src.repositories import orders as orders_repo
from src.schemas.orders import OrderCreate, OrderRead, OrderUser

logger = logging.getLogger(__name__)


async def get_order_enriched(session: AsyncSession, order_id: UUID) -> OrderUser:
    order = await orders_repo.get_order_with_items(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    user = await users_client.get_user(order.user_id)

    return OrderUser(
        order=OrderRead.model_validate(order),
        user=user,
    )


async def create_order(session: AsyncSession, data: OrderCreate) -> OrderUser:
    user = await users_client.get_user(data.user_id)

    order = await orders_repo.create_order(session, data)
    logger.info("order created order_id=%s", order.id)

    return OrderUser(
        order=OrderRead.model_validate(order),
        user=user,
    )
