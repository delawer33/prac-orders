from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.order_creation_sagas import (
    OrderCreationSagaModel,
    OrderCreationSagaStatus,
)

MAX_COMPENSATION_RETRIES = 10


async def get_by_key(
    session: AsyncSession,
    idempotency_key: str,
) -> OrderCreationSagaModel | None:
    result = await session.execute(
        select(OrderCreationSagaModel).where(OrderCreationSagaModel.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


async def create_or_get(
    session: AsyncSession,
    *,
    idempotency_key: str,
    request_fingerprint: str,
    email: str | None,
) -> OrderCreationSagaModel:
    existing = await get_by_key(session, idempotency_key)
    if existing:
        return existing

    saga = OrderCreationSagaModel(
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        email=email,
        status=OrderCreationSagaStatus.USER_CREATE_REQUESTED,
    )
    session.add(saga)
    await session.flush()
    await session.refresh(saga)
    return saga


async def mark_user_created(
    session: AsyncSession,
    saga: OrderCreationSagaModel,
    *,
    user_id: UUID,
    user_created: bool,
) -> None:
    saga.resolved_user_id = user_id
    saga.resolved_user_created = user_created
    saga.status = OrderCreationSagaStatus.USER_CREATED
    await session.flush()


async def mark_order_created(
    session: AsyncSession,
    saga: OrderCreationSagaModel,
    *,
    order_id: UUID,
) -> None:
    saga.order_id = order_id
    saga.status = OrderCreationSagaStatus.ORDER_CREATED
    await session.flush()


async def mark_compensation_pending(
    session: AsyncSession,
    saga: OrderCreationSagaModel,
    *,
    error: str,
    retry_delay_seconds: int = 0,
) -> None:
    saga.status = OrderCreationSagaStatus.COMPENSATION_PENDING
    saga.last_error = error
    saga.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=retry_delay_seconds)
    await session.flush()


async def mark_compensated(
    session: AsyncSession,
    saga: OrderCreationSagaModel,
) -> None:
    saga.status = OrderCreationSagaStatus.COMPENSATED
    saga.last_error = None
    saga.next_retry_at = None
    await session.flush()


async def mark_failed(
    session: AsyncSession,
    saga: OrderCreationSagaModel,
    *,
    error: str,
) -> None:
    saga.status = OrderCreationSagaStatus.FAILED
    saga.last_error = error
    saga.next_retry_at = None
    await session.flush()


async def schedule_retry(
    session: AsyncSession,
    saga: OrderCreationSagaModel,
    *,
    error: str,
) -> None:
    saga.retry_count += 1
    saga.last_error = error
    delay_seconds = min(2 ** saga.retry_count, 300)
    saga.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    if saga.retry_count >= MAX_COMPENSATION_RETRIES:
        saga.status = OrderCreationSagaStatus.FAILED
        saga.next_retry_at = None
    else:
        saga.status = OrderCreationSagaStatus.COMPENSATION_PENDING
    await session.flush()


async def lock_pending_compensations(
    session: AsyncSession,
    *,
    limit: int,
) -> list[OrderCreationSagaModel]:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(OrderCreationSagaModel)
        .where(OrderCreationSagaModel.status == OrderCreationSagaStatus.COMPENSATION_PENDING)
        .where(
            (OrderCreationSagaModel.next_retry_at.is_(None))
            | (OrderCreationSagaModel.next_retry_at <= now)
        )
        .order_by(OrderCreationSagaModel.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars())


async def lock_recovery_candidates(
    session: AsyncSession,
    *,
    limit: int,
    stale_before: datetime,
) -> list[OrderCreationSagaModel]:
    result = await session.execute(
        select(OrderCreationSagaModel)
        .where(
            OrderCreationSagaModel.status.in_(
                [
                    OrderCreationSagaStatus.USER_CREATE_REQUESTED,
                    OrderCreationSagaStatus.USER_CREATED,
                ]
            )
        )
        .where(OrderCreationSagaModel.updated_at <= stale_before)
        .order_by(OrderCreationSagaModel.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars())


async def lock_by_id(
    session: AsyncSession,
    *,
    saga_id: UUID,
) -> OrderCreationSagaModel | None:
    result = await session.execute(
        select(OrderCreationSagaModel)
        .where(OrderCreationSagaModel.id == saga_id)
        .with_for_update(skip_locked=True)
    )
    return result.scalar_one_or_none()
