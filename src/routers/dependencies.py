from typing import Annotated

from fastapi import Depends

from src.db import SessionDep
from src.repositories.orders import OrdersRepository
from src.services.orders import OrdersService


def get_orders_repository(session: SessionDep) -> OrdersRepository:
    return OrdersRepository(session)


def get_orders_service(
    repository: Annotated[OrdersRepository, Depends(get_orders_repository)],
) -> OrdersService:
    return OrdersService(repository)


OrdersRepositoryDep = Annotated[OrdersRepository, Depends(get_orders_repository)]
OrdersServiceDep = Annotated[OrdersService, Depends(get_orders_service)]
