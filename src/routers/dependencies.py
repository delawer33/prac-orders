from typing import Annotated

from fastapi import Depends

from src.db import SessionDep
from src.repositories.order_creation_sagas import OrderCreationSagaRepository
from src.repositories.orders import OrdersRepository
from src.services.orders import OrdersService


def get_orders_repository(session: SessionDep) -> OrdersRepository:
    return OrdersRepository(session)


def get_order_creation_saga_repository(session: SessionDep) -> OrderCreationSagaRepository:
    return OrderCreationSagaRepository(session)


def get_orders_service(
    repository: Annotated[OrdersRepository, Depends(get_orders_repository)],
    saga_repository: Annotated[
        OrderCreationSagaRepository,
        Depends(get_order_creation_saga_repository),
    ],
) -> OrdersService:
    return OrdersService(repository, saga_repository)


OrdersRepositoryDep = Annotated[OrdersRepository, Depends(get_orders_repository)]
OrdersServiceDep = Annotated[OrdersService, Depends(get_orders_service)]
