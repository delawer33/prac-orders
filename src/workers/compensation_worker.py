import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from src.clients import users_client
from src.config import Settings
from src.db import SessionFactory
from src.models.order_creation_sagas import OrderCreationSagaStatus
from src.repositories.order_creation_sagas import OrderCreationSagaRepository

logger = logging.getLogger(__name__)
settings = Settings()
# Воркер в цикле выполняет две фазы: (1) recovery "зависших" саг, (2) обработку компенсаций
# со статусом COMPENSATION_PENDING. Каждая сага обрабатывается в отдельной транзакции


async def _mark_order_not_created(
    saga_repository: OrderCreationSagaRepository,
    *,
    saga,
    reason: str,
    details: str,
) -> None:
    await saga_repository.mark_failed(
        saga=saga,
        error_code="order_not_created",
        error_message=f"{reason}: {details}",
    )


async def _recover_user_resolved_saga(
    saga_repository: OrderCreationSagaRepository,
    *,
    saga,
    reason: str,
) -> None:
    if not saga.resolved_user_created:
        # Пользователь существовал заранее, компенсация не требуется
        await _mark_order_not_created(
            saga_repository,
            saga=saga,
            reason=reason,
            details="order was not created (existing user, no compensation)",
        )
        return

    await saga_repository.mark_compensation_pending(
        saga=saga,
        error=f"{reason}: user created without order",
    )


async def _recover_started_saga(
    saga_repository: OrderCreationSagaRepository,
    client,
    *,
    saga,
    reason: str,
) -> None:
    # Для started-саги email обязателен для повторного resolve
    if not saga.email:
        await saga_repository.mark_failed(
            saga=saga,
            error_code="invalid_saga_state",
            error_message=f"{reason}: missing email for stale started saga",
        )
        return

    resolve_data = await users_client.resolve_user(
        client,
        saga.email,
        saga.idempotency_key,
    )
    resolved_user = resolve_data["user"]
    resolved_created = resolve_data["created"]
    await saga_repository.mark_user_resolved(
        saga=saga,
        user_id=UUID(resolved_user["id"]),
        user_created=resolved_created,
    )
    if resolved_created:
        # Если пользователя создали в рамках текущей саги, при сбое дальше нужна компенсация
        await saga_repository.mark_compensation_pending(
            saga=saga,
            error=f"{reason}: user created during reconciliation",
        )
        return

    # Если resolve вернул существующего пользователя, компенсировать нечего
    await _mark_order_not_created(
        saga_repository,
        saga=saga,
        reason=reason,
        details="resolve returned existing user, no compensation",
    )


async def _recover_saga(session, client, *, saga, reason: str) -> None:
    saga_repository = OrderCreationSagaRepository(session)
    if saga.status == OrderCreationSagaStatus.USER_RESOLVED:
        await _recover_user_resolved_saga(
            saga_repository,
            saga=saga,
            reason=reason,
        )
        return

    if saga.status != OrderCreationSagaStatus.STARTED:
        await saga_repository.mark_failed(
            saga=saga,
            error_code="invalid_saga_state",
            error_message=f"{reason}: unsupported recovery status={saga.status}",
        )
        return

    await _recover_started_saga(
        saga_repository,
        client,
        saga=saga,
        reason=reason,
    )


async def _run_recovery_pass(client, *, reason: str) -> None:
    # Сначала берем кандидатов в отдельной транзакции и фиксируем список id
    stale_before = datetime.now(timezone.utc) - timedelta(
        seconds=settings.saga_recovery_grace_seconds
    )
    async with SessionFactory() as session:
        saga_repository = OrderCreationSagaRepository(session)
        try:
            sagas = await saga_repository.lock_recovery_candidates(
                limit=settings.saga_worker_batch_size,
                stale_before=stale_before,
            )
            saga_ids = [saga.id for saga in sagas]
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("failed to load recovery candidates reason=%s", reason)
            return

    for saga_id in saga_ids:
        async with SessionFactory() as session:
            saga_repository = OrderCreationSagaRepository(session)
            try:
                saga = await saga_repository.lock_by_id(saga_id=saga_id)
                if not saga:
                    await session.commit()
                    continue
                await _recover_saga(session, client, saga=saga, reason=reason)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "recovery failed for saga_id=%s reason=%s",
                    saga_id,
                    reason,
                )


async def _run_startup_recovery(client) -> None:
    await _run_recovery_pass(client, reason="startup recovery")


async def _process_pending_compensations(client) -> None:
    async with SessionFactory() as session:
        saga_repository = OrderCreationSagaRepository(session)
        try:
            sagas = await saga_repository.lock_pending_compensations(
                limit=settings.saga_worker_batch_size,
            )
            if not sagas:
                await session.commit()
                return

            for saga in sagas:
                if saga.resolved_user_id is None:
                    # Компенсация невозможна без id пользователя
                    await saga_repository.mark_failed(
                        saga=saga,
                        error_code="compensation_failed",
                        error_message="Compensation failed: missing resolved_user_id",
                    )
                    continue
                try:
                    # Компенсация
                    await users_client.cancel_user_for_order_saga(client, saga.resolved_user_id)
                    await saga_repository.mark_compensated(saga=saga)
                    logger.info(
                        "saga compensated idempotency_key=%s saga_id=%s user_id=%s",
                        saga.idempotency_key,
                        saga.id,
                        saga.resolved_user_id,
                    )
                except Exception as exc:
                    # Ошибки компенсации переводим в retry с backoff до исчерпания лимита
                    await saga_repository.schedule_retry(
                        saga=saga,
                        error=f"compensation failed: {exc}",
                    )
                    logger.warning(
                        "saga compensation retry scheduled idempotency_key=%s saga_id=%s retry_count=%s",
                        saga.idempotency_key,
                        saga.id,
                        saga.retry_count,
                    )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def run_worker() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    client = users_client.create_http_client()
    try:
        await _run_startup_recovery(client)
        while True:
            try:
                await _run_recovery_pass(client, reason="periodic recovery")
                await _process_pending_compensations(client)
            except Exception:
                logger.exception("worker iteration failed")
            await asyncio.sleep(settings.saga_worker_poll_interval_seconds)
    finally:
        await users_client.close_http_client(client)


if __name__ == "__main__":
    asyncio.run(run_worker())
