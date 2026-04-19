from uuid import UUID

from fastapi import APIRouter

from src.db import SessionDep
from src.schemas.orders import OrderCreate, OrderUser
from src.services import orders as orders_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderUser)
async def get_order(order_id: UUID, session: SessionDep) -> OrderUser:
    return await orders_service.get_order_enriched(session, order_id)


@router.post("/", response_model=OrderUser, status_code=201)
async def create_order(data: OrderCreate, session: SessionDep) -> OrderUser:
    return await orders_service.create_order(session, data)
