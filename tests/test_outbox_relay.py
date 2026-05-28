from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiokafka.errors import KafkaConnectionError

from src.models.order_feedback_outbox import OrderFeedbackCreatedOutboxModel, OrderFeedbackOutboxStatus
from src.workers.order_feedback_outbox_relay import OrderFeedbackOutboxRelay


def _row(*, status: str = OrderFeedbackOutboxStatus.PENDING) -> OrderFeedbackCreatedOutboxModel:
    feedback_id = uuid4()
    order_id = uuid4()
    user_id = uuid4()
    return OrderFeedbackCreatedOutboxModel(
        id=uuid4(),
        event_id=feedback_id,
        status=status,
        payload={
            "event_id": str(feedback_id),
            "event_type": "OrderFeedbackCreated",
            "occurred_at": "2024-06-01T12:00:00+00:00",
            "data": {
                "feedback_id": str(feedback_id),
                "order_id": str(order_id),
                "user_id": str(user_id),
            },
        },
    )


def _relay() -> OrderFeedbackOutboxRelay:
    return OrderFeedbackOutboxRelay(AsyncMock())


@pytest.mark.asyncio
async def test_relay_rows_batch_marks_after_all_sends() -> None:
    relay = _relay()
    rows = [_row(), _row()]

    with patch.object(relay, "_mark_batch_published", new_callable=AsyncMock) as mark:
        await relay._relay_rows(rows)

    assert relay._producer.send_and_wait.await_count == 2
    mark.assert_awaited_once_with(rows)


@pytest.mark.asyncio
async def test_relay_rows_stops_on_kafka_error_marks_only_sent_rows() -> None:
    relay = _relay()
    relay._producer.send_and_wait.side_effect = [None, KafkaConnectionError("down")]
    rows = [_row(), _row()]

    with patch.object(relay, "_mark_batch_published", new_callable=AsyncMock) as mark:
        await relay._relay_rows(rows)

    assert relay._producer.send_and_wait.await_count == 2
    mark.assert_awaited_once_with([rows[0]])


@pytest.mark.asyncio
async def test_reclaim_processing_calls_repo_and_commits() -> None:
    relay = _relay()
    repo = MagicMock()
    repo.reclaim_processing = AsyncMock()
    session = AsyncMock()

    with (
        patch("src.workers.order_feedback_outbox_relay.SessionFactory") as session_factory,
        patch("src.workers.order_feedback_outbox_relay.OrderFeedbackOutboxRepository", return_value=repo),
    ):
        session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        await relay._reclaim_processing()

    repo.reclaim_processing.assert_awaited_once_with(
        timeout_seconds=relay._settings.kafka_outbox_processing_timeout_seconds
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_pending_rows_claims_and_relays() -> None:
    relay = _relay()
    row = _row()
    repo = MagicMock()
    repo.claim_pending_batch = AsyncMock(return_value=[row])
    session = AsyncMock()

    with (
        patch("src.workers.order_feedback_outbox_relay.SessionFactory") as session_factory,
        patch("src.workers.order_feedback_outbox_relay.OrderFeedbackOutboxRepository", return_value=repo),
        patch.object(relay, "_relay_rows", new_callable=AsyncMock) as relay_rows,
    ):
        session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        await relay._publish_pending_rows()

    repo.claim_pending_batch.assert_awaited_once()
    relay_rows.assert_awaited_once_with([row])
