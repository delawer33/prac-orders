import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from src.clients import users_client
from src.config import Settings
from src.db import SessionFactory
from src.models.order_creation_sagas import OrderCreationSagaStatus
from src.repositories import order_idempotency_keys as idempotency_repo
from src.repositories import order_creation_sagas as saga_repo

logger = logging.getLogger(__name__)
settings = Settings()


async def _mark_idempotency_failed(
    *,
    session,
    idempotency_key: str,
    error_code: str,
    error_message: str,
) -> None:
    idempotency_record = await idempotency_repo.get_key(session, idempotency_key)
    if not idempotency_record:
        return
    await idempotency_repo.mark_key_failed(
        session=session,
        record=idempotency_record,
        error_code=error_code,
        error_message=error_message,
    )


async def _recover_saga(session, client, *, saga, reason: str) -> None:
    # Ветка восстановления для саги, где пользователь уже определен
    if saga.status == OrderCreationSagaStatus.USER_CREATED:
        if not saga.resolved_user_created:
            # Пользователь существовал заранее, компенсация не требуется
            await saga_repo.mark_failed(
                session=session,
                saga=saga,
                error=f"{reason}: resolved existing user, compensation not required",
            )
            await _mark_idempotency_failed(
                session=session,
                idempotency_key=saga.idempotency_key,
                error_code="order_not_created",
                error_message=f"{reason}: order was not created",
            )
            return
        await saga_repo.mark_compensation_pending(
            session=session,
            saga=saga,
            error=f"{reason}: user created without order",
        )
        return

    # Для USER_CREATE_REQUESTED email обязателен для повторного resolve
    if not saga.email:
        await saga_repo.mark_failed(
            session=session,
            saga=saga,
            error=f"{reason}: missing email for user_create_requested",
        )
        await _mark_idempotency_failed(
            session=session,
            idempotency_key=saga.idempotency_key,
            error_code="invalid_saga_state",
            error_message=f"{reason}: missing email for unresolved saga",
        )
        return

    resolve_data = await users_client.resolve_user(
        client,
        saga.email,
        saga.idempotency_key,
    )
    resolved_user = resolve_data["user"]
    resolved_created = resolve_data["created"]
    await saga_repo.mark_user_created(
        session=session,
        saga=saga,
        user_id=UUID(resolved_user["id"]),
        user_created=resolved_created,
    )
    if resolved_created:
        # Если пользователя создали в рамках текущей саги, при сбое дальше нужна компенсация
        await saga_repo.mark_compensation_pending(
            session=session,
            saga=saga,
            error=f"{reason}: user created during reconciliation",
        )
        return
    # Если resolve вернул существующего пользователя, компенсировать нечего
    await saga_repo.mark_failed(
        session=session,
        saga=saga,
        error=f"{reason}: resolve returned existing user, compensation not required",
    )
    await _mark_idempotency_failed(
        session=session,
        idempotency_key=saga.idempotency_key,
        error_code="order_not_created",
        error_message=f"{reason}: order was not created",
    )


async def _run_recovery_pass(client, *, reason: str) -> None:
    # Сначала берем кандидатов в отдельной транзакции и фиксируем список id
    stale_before = datetime.now(timezone.utc) - timedelta(
        seconds=settings.saga_recovery_grace_seconds
    )
    async with SessionFactory() as session:
        try:
            sagas = await saga_repo.lock_recovery_candidates(
                session,
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
            try:
                saga = await saga_repo.lock_by_id(session, saga_id=saga_id)
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
        try:
            sagas = await saga_repo.lock_pending_compensations(
                session,
                limit=settings.saga_worker_batch_size,
            )
            if not sagas:
                await session.commit()
                return

            for saga in sagas:
                if saga.resolved_user_id is None:
                    # Компенсация невозможна без id пользователя
                    await saga_repo.mark_failed(
                        session=session,
                        saga=saga,
                        error="compensation skipped: missing resolved_user_id",
                    )
                    await _mark_idempotency_failed(
                        session=session,
                        idempotency_key=saga.idempotency_key,
                        error_code="compensation_failed",
                        error_message="Compensation failed: missing resolved_user_id",
                    )
                    continue
                try:
                    await users_client.delete_user(client, saga.resolved_user_id)
                    # Успешная компенсация переводит сагу в COMPENSATED и ключ в FAILED
                    await saga_repo.mark_compensated(session=session, saga=saga)
                    await _mark_idempotency_failed(
                        session=session,
                        idempotency_key=saga.idempotency_key,
                        error_code="compensated",
                        error_message="Order creation failed and user compensation completed",
                    )
                    logger.info(
                        "saga compensated idempotency_key=%s saga_id=%s user_id=%s",
                        saga.idempotency_key,
                        saga.id,
                        saga.resolved_user_id,
                    )
                except Exception as exc:
                    # Ошибки компенсации переводим в retry с backoff до исчерпания лимита
                    await saga_repo.schedule_retry(
                        session=session,
                        saga=saga,
                        error=f"compensation failed: {exc}",
                    )
                    if saga.status == OrderCreationSagaStatus.FAILED:
                        await _mark_idempotency_failed(
                            session=session,
                            idempotency_key=saga.idempotency_key,
                            error_code="compensation_failed",
                            error_message=f"Compensation retries exhausted: {exc}",
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
