from typing import Annotated

from fastapi import Depends

from src.db import SessionDep
from src.repositories.order_creation_sagas import OrderCreationSagaRepository
from src.repositories.order_feedbacks import OrderFeedbacksRepository
from src.repositories.orders import OrdersRepository
from src.repositories.order_feedback_outbox import OrderFeedbackOutboxRepository
from src.services.order_feedbacks import OrderFeedbacksService
from src.services.orders import OrdersService


def get_orders_repository(session: SessionDep) -> OrdersRepository:
    return OrdersRepository(session)


def get_order_creation_saga_repository(session: SessionDep) -> OrderCreationSagaRepository:
    return OrderCreationSagaRepository(session)


def get_outbox_repository(session: SessionDep) -> OrderFeedbackOutboxRepository:
    return OrderFeedbackOutboxRepository(session)


def get_order_feedbacks_repository(session: SessionDep) -> OrderFeedbacksRepository:
    return OrderFeedbacksRepository(session)


def get_orders_service(
    repository: Annotated[OrdersRepository, Depends(get_orders_repository)],
    saga_repository: Annotated[
        OrderCreationSagaRepository,
        Depends(get_order_creation_saga_repository),
    ],
) -> OrdersService:
    return OrdersService(repository, saga_repository)


def get_order_feedbacks_service(
    feedbacks_repository: Annotated[
        OrderFeedbacksRepository, Depends(get_order_feedbacks_repository)
    ],
    orders_repository: Annotated[OrdersRepository, Depends(get_orders_repository)],
    outbox_repository: Annotated[OrderFeedbackOutboxRepository, Depends(get_outbox_repository)],
) -> OrderFeedbacksService:
    return OrderFeedbacksService(
        feedbacks_repository,
        orders_repository,
        outbox_repository,
    )


OrdersRepositoryDep = Annotated[OrdersRepository, Depends(get_orders_repository)]
OrdersServiceDep = Annotated[OrdersService, Depends(get_orders_service)]
OrderFeedbacksServiceDep = Annotated[OrderFeedbacksService, Depends(get_order_feedbacks_service)]
