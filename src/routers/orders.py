from uuid import UUID

from fastapi import APIRouter, Header

from src.clients.users_client import UsersHttpClientDep
from .dependencies import OrdersServiceDep
from src.schemas.orders import OrderCreate, OrderUser

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderUser)
async def get_order(
    order_id: UUID,
    service: OrdersServiceDep,
    users_http_client: UsersHttpClientDep,
) -> OrderUser:
    return await service.get_order_enriched(users_http_client, order_id)


@router.post("/", response_model=OrderUser, status_code=201)
async def create_order(
    data: OrderCreate,
    service: OrdersServiceDep,
    users_http_client: UsersHttpClientDep,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> OrderUser:
    return await service.create_order(users_http_client, data, idempotency_key)
