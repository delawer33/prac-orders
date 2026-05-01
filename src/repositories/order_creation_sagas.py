from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.order_creation_sagas import (
    OrderCreationSagaModel,
    OrderCreationSagaStatus,
)

MAX_COMPENSATION_RETRIES = 10


class OrderCreationSagaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_key(self, idempotency_key: str) -> OrderCreationSagaModel | None:
        result = await self.session.execute(
            select(OrderCreationSagaModel).where(OrderCreationSagaModel.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def create_or_get(
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        email: str | None,
    ) -> OrderCreationSagaModel:
        existing = await self.get_by_key(idempotency_key)
        if existing:
            return existing

        saga = OrderCreationSagaModel(
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            email=email,
            status=OrderCreationSagaStatus.STARTED,
        )
        self.session.add(saga)
        try:
            await self.session.flush()
        except IntegrityError:
            # Гонка: другой запрос уже вставил сагу с тем же ключом — откатываем и читаем существующую
            await self.session.rollback()
            existing = await self.get_by_key(idempotency_key)
            if existing:
                return existing
            raise
        await self.session.refresh(saga)
        return saga

    async def mark_user_resolved(
        self,
        saga: OrderCreationSagaModel,
        *,
        user_id: UUID,
        user_created: bool,
    ) -> None:
        saga.resolved_user_id = user_id
        saga.resolved_user_created = user_created
        saga.status = OrderCreationSagaStatus.USER_RESOLVED
        await self.session.flush()

    async def mark_order_created(
        self,
        saga: OrderCreationSagaModel,
        *,
        order_id: UUID,
        response_body: dict,
    ) -> None:
        saga.order_id = order_id
        saga.status = OrderCreationSagaStatus.ORDER_CREATED
        saga.response_body = response_body
        saga.error_code = None
        saga.error_message = None
        await self.session.flush()

    async def mark_compensation_pending(
        self,
        saga: OrderCreationSagaModel,
        *,
        error: str,
        retry_delay_seconds: int = 0,
    ) -> None:
        saga.status = OrderCreationSagaStatus.COMPENSATION_PENDING
        saga.error_message = error
        saga.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=retry_delay_seconds)
        await self.session.flush()

    async def mark_compensated(self, saga: OrderCreationSagaModel) -> None:
        saga.status = OrderCreationSagaStatus.COMPENSATED
        saga.next_retry_at = None
        saga.response_body = None
        saga.error_code = "compensated"
        saga.error_message = "Order creation failed; user left inactive (saga compensation completed)"
        await self.session.flush()

    async def mark_failed(
        self,
        saga: OrderCreationSagaModel,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        saga.status = OrderCreationSagaStatus.FAILED
        saga.next_retry_at = None
        saga.response_body = None
        saga.error_code = error_code
        saga.error_message = error_message
        await self.session.flush()

    async def schedule_retry(
        self,
        saga: OrderCreationSagaModel,
        *,
        error: str,
    ) -> None:
        saga.retry_count += 1
        saga.error_message = error
        delay_seconds = min(2**saga.retry_count, 300)
        saga.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        if saga.retry_count >= MAX_COMPENSATION_RETRIES:
            saga.status = OrderCreationSagaStatus.FAILED
            saga.next_retry_at = None
            saga.error_code = "compensation_failed"
            saga.error_message = f"Compensation retries exhausted: {error}"
        else:
            saga.status = OrderCreationSagaStatus.COMPENSATION_PENDING
        await self.session.flush()

    async def lock_pending_compensations(
        self,
        *,
        limit: int,
    ) -> list[OrderCreationSagaModel]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
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
        self,
        *,
        limit: int,
        stale_before: datetime,
    ) -> list[OrderCreationSagaModel]:
        result = await self.session.execute(
            select(OrderCreationSagaModel)
            .where(
                OrderCreationSagaModel.status.in_(
                    [
                        OrderCreationSagaStatus.STARTED,
                        OrderCreationSagaStatus.USER_RESOLVED,
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
        self,
        *,
        saga_id: UUID,
    ) -> OrderCreationSagaModel | None:
        result = await self.session.execute(
            select(OrderCreationSagaModel)
            .where(OrderCreationSagaModel.id == saga_id)
            .with_for_update(skip_locked=True)
        )
        return result.scalar_one_or_none()
