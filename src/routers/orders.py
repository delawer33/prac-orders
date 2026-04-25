from uuid import UUID

from fastapi import APIRouter, Header

from src.clients.users_client import UsersHttpClientDep
from src.db import SessionDep
from src.schemas.orders import OrderCreate, OrderUser
from src.services import orders as orders_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderUser)
async def get_order(
    order_id: UUID,
    session: SessionDep,
    users_http_client: UsersHttpClientDep,
) -> OrderUser:
    return await orders_service.get_order_enriched(session, users_http_client, order_id)


@router.post("/", response_model=OrderUser, status_code=201)
async def create_order(
    data: OrderCreate,
    session: SessionDep,
    users_http_client: UsersHttpClientDep,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> OrderUser:
    return await orders_service.create_order(
        session=session,
        users_http_client=users_http_client,
        data=data,
        idempotency_key=idempotency_key,
    )
