from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import IdempotencyKeyAlreadyExistsError
from src.models.order_idempotency_keys import OrderIdempotencyKeyModel, OrderIdempotencyStatus


async def get_key(session: AsyncSession, key: str) -> OrderIdempotencyKeyModel | None:
    result = await session.execute(
        select(OrderIdempotencyKeyModel).where(OrderIdempotencyKeyModel.key == key)
    )
    return result.scalar_one_or_none()


async def reserve_key(
    session: AsyncSession,
    key: str,
    request_fingerprint: str,
) -> OrderIdempotencyKeyModel:
    record = OrderIdempotencyKeyModel(
        key=key,
        request_fingerprint=request_fingerprint,
        status=OrderIdempotencyStatus.PROCESSING,
    )
    session.add(record)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise IdempotencyKeyAlreadyExistsError(key) from exc
    await session.refresh(record)
    return record


async def complete_key(
    session: AsyncSession,
    record: OrderIdempotencyKeyModel,
    order_id,
    response_body: dict,
) -> None:
    record.status = OrderIdempotencyStatus.SUCCEEDED
    record.order_id = order_id
    record.response_body = response_body
    record.error_code = None
    record.error_message = None
    await session.flush()


async def mark_key_failed(
    session: AsyncSession,
    record: OrderIdempotencyKeyModel,
    *,
    error_code: str,
    error_message: str,
) -> None:
    record.status = OrderIdempotencyStatus.FAILED
    record.error_code = error_code
    record.error_message = error_message
    await session.flush()


async def delete_key(session: AsyncSession, record: OrderIdempotencyKeyModel) -> None:
    await session.delete(record)
    await session.flush()
