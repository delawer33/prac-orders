from decimal import Decimal
from uuid import uuid4

import pytest

from src.repositories.order_creation_sagas import OrderCreationSagaRepository
from src.repositories.orders import OrdersRepository
from src.repositories.outbox import OutboxRepository
from src.schemas.orders import OrderCreate, OrderItemCreate
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


def _make_service(db_session):
    return OrdersService(
        repo=OrdersRepository(db_session),
        saga_repo=OrderCreationSagaRepository(db_session),
        outbox_repo=OutboxRepository(db_session),
    )


async def test_create_order_writes_pending_outbox_row(db_session):
    users_gateway = FakeUsersGateway({str(_FAKE_USER_ID): _FAKE_USER})
    service = _make_service(db_session)

    data = OrderCreate(
        user_id=_FAKE_USER_ID,
        title="Test Order",
        items=[
            OrderItemCreate(product_name="Widget", quantity=2, price=9.99),
            OrderItemCreate(product_name="Gadget", quantity=1, price=5.00),
        ],
    )

    result = await service.create_order(users_gateway, data, idempotency_key="key-1")

    outbox_repo = OutboxRepository(db_session)
    pending = await outbox_repo.get_pending_batch(limit=10)

    assert len(pending) == 1
    row = pending[0]
    assert row.event_id == result.order.id
    assert row.status == "pending"

    payload = row.payload
    assert payload["event_type"] == "OrderCreated"
    assert payload["data"]["order_id"] == str(result.order.id)
    assert payload["data"]["user_id"] == str(_FAKE_USER_ID)
    expected_total = round(2 * 9.99 + 1 * 5.00, 2)
    assert abs(payload["data"]["total_amount"] - expected_total) < 0.001
