from uuid import UUID

from fastapi import APIRouter, Header

from src.clients.users_client import UsersGatewayDep
from .dependencies import OrdersServiceDep
from src.schemas.orders import OrderCreate, OrderUser

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderUser)
async def get_order(
    order_id: UUID,
    service: OrdersServiceDep,
    users_gateway: UsersGatewayDep,
) -> OrderUser:
    return await service.get_order_enriched(users_gateway, order_id)


@router.post("/", response_model=OrderUser, status_code=201)
async def create_order(
    data: OrderCreate,
    service: OrdersServiceDep,
    users_gateway: UsersGatewayDep,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> OrderUser:
    return await service.create_order(users_gateway, data, idempotency_key)
