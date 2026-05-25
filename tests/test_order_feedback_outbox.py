from uuid import uuid4

import pytest

from src.repositories.order_creation_sagas import OrderCreationSagaRepository
from src.repositories.order_feedbacks import OrderFeedbacksRepository
from src.repositories.orders import OrdersRepository
from src.repositories.order_feedback_outbox import OrderFeedbackOutboxRepository
from src.schemas.feedbacks import FeedbackCreate
from src.schemas.orders import OrderCreate, OrderItemCreate
from src.services.order_feedbacks import OrderFeedbacksService
from src.services.orders import OrdersService
from tests.conftest import FakeUsersGateway

_FAKE_USER_ID = uuid4()
_FAKE_USER = {
    "id": str(_FAKE_USER_ID),
    "username": "alice",
    "email": "alice@example.com",
    "first_name": "Alice",
    "last_name": "Smith",
    "is_active": True,
    "created_at": "2024-01-01T00:00:00",
}


def _make_orders_service(db_session):
    return OrdersService(
        repo=OrdersRepository(db_session),
        saga_repo=OrderCreationSagaRepository(db_session),
    )


def _make_feedbacks_service(db_session):
    return OrderFeedbacksService(
        feedbacks_repo=OrderFeedbacksRepository(db_session),
        orders_repo=OrdersRepository(db_session),
        outbox_repo=OrderFeedbackOutboxRepository(db_session),
    )


async def test_create_order_does_not_write_outbox_row(db_session):
    users_gateway = FakeUsersGateway({str(_FAKE_USER_ID): _FAKE_USER})
    service = _make_orders_service(db_session)

    data = OrderCreate(
        user_id=_FAKE_USER_ID,
        title="Test Order",
        items=[OrderItemCreate(product_name="Widget", quantity=1, price=9.99)],
    )

    await service.create_order(users_gateway, data, idempotency_key="key-1")

    outbox_repo = OrderFeedbackOutboxRepository(db_session)
    pending = await outbox_repo.get_pending_batch(limit=10)
    assert pending == []


async def test_create_feedback_writes_pending_outbox_row(db_session):
    users_gateway = FakeUsersGateway({str(_FAKE_USER_ID): _FAKE_USER})
    orders_service = _make_orders_service(db_session)
    feedbacks_service = _make_feedbacks_service(db_session)

    order_result = await orders_service.create_order(
        users_gateway,
        OrderCreate(
            user_id=_FAKE_USER_ID,
            title="Test Order",
            items=[OrderItemCreate(product_name="Widget", quantity=1, price=5.00)],
        ),
        idempotency_key="key-1",
    )

    result = await feedbacks_service.create_feedback(
        FeedbackCreate(order_id=order_result.order.id, text="Great order"),
    )

    outbox_repo = OrderFeedbackOutboxRepository(db_session)
    pending = await outbox_repo.get_pending_batch(limit=10)

    assert len(pending) == 1
    row = pending[0]
    assert row.event_id == result.id
    assert row.status == "pending"

    payload = row.payload
    assert payload["event_type"] == "OrderFeedbackCreated"
    assert payload["event_id"] == str(result.id)
    assert payload["data"]["feedback_id"] == str(result.id)
    assert payload["data"]["order_id"] == str(order_result.order.id)
    assert payload["data"]["user_id"] == str(_FAKE_USER_ID)
    assert "text" not in payload["data"]
