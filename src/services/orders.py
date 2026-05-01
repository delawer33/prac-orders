import hashlib
import json
import logging
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients import users_client
from src.exceptions import (
    DownstreamUserNotFoundError,
    IdempotencyConflictError,
    IdempotencyFailedError,
    IdempotencyInProgressError,
    OrderNotFoundError,
    SagaInvariantError,
    UsersServiceError,
    UsersServiceUnavailableError,
)
from src.models.order_creation_sagas import OrderCreationSagaModel, OrderCreationSagaStatus
from src.repositories.order_creation_sagas import OrderCreationSagaRepository
from src.repositories import orders as orders_repo
from src.schemas.orders import OrderCreate, OrderRead, OrderUser, UserRead, UserResolveResponse

logger = logging.getLogger(__name__)


def _build_request_fingerprint(data: OrderCreate) -> str:
    payload = data.model_dump(mode="json", exclude_none=True)
    raw_value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def _resolve_replay_from_saga(
    saga: OrderCreationSagaModel,
    *,
    request_fingerprint: str,
) -> OrderUser:
    if saga.request_fingerprint != request_fingerprint:
        raise IdempotencyConflictError(saga.idempotency_key)
    if saga.status == OrderCreationSagaStatus.ORDER_CREATED and saga.response_body is not None:
        return OrderUser.model_validate(saga.response_body)
    if saga.status in {OrderCreationSagaStatus.FAILED, OrderCreationSagaStatus.COMPENSATED}:
        raise IdempotencyFailedError(saga.idempotency_key, reason=saga.error_message)
    raise IdempotencyInProgressError(saga.idempotency_key)


async def _try_replay_existing_saga(
    saga_repository: OrderCreationSagaRepository,
    *,
    idempotency_key: str,
    request_fingerprint: str,
) -> OrderUser | None:
    # Уже есть сага по ключу — отдаём сохранённый результат или ошибку идемпотентности
    existing_saga = await saga_repository.get_by_key(idempotency_key)
    if not existing_saga:
        return None
    return _resolve_replay_from_saga(
        existing_saga,
        request_fingerprint=request_fingerprint,
    )


async def _reload_saga_after_first_commit(
    saga_repository: OrderCreationSagaRepository,
    *,
    idempotency_key: str,
    request_fingerprint: str,
) -> OrderUser | OrderCreationSagaModel:
    saga = await saga_repository.get_by_key(idempotency_key)
    if not saga:
        raise SagaInvariantError("saga missing after create_or_get")
    # Параллельный запрос мог продвинуть сагу — отдаём тот же ответ, что и при повторе ключа
    if saga.status != OrderCreationSagaStatus.STARTED:
        return _resolve_replay_from_saga(saga, request_fingerprint=request_fingerprint)
    return saga


async def _mark_saga_after_user_resolution_failure(
    session: AsyncSession,
    saga_repository: OrderCreationSagaRepository,
    idempotency_key: str,
) -> None:
    await session.rollback()
    saga = await saga_repository.get_by_key(idempotency_key)
    if saga:
        # Не удалось достучаться до users / валидация — финализируем сагу как ошибочную
        await saga_repository.mark_failed(
            saga=saga,
            error_code="user_resolution_failed",
            error_message="User resolution failed",
        )
        await session.commit()


async def _resolve_user_step(
    session: AsyncSession,
    users_http_client: httpx.AsyncClient,
    saga_repository: OrderCreationSagaRepository,
    saga: OrderCreationSagaModel,
    data: OrderCreate,
    idempotency_key: str,
) -> UserRead:
    try:
        if data.user_id is not None:
            user_data = await users_client.get_user(users_http_client, data.user_id)
            user = UserRead.model_validate(user_data)
            resolved_user_created = False
        else:
            # external_request_id == idempotency_key делает резолв пользователя
            # идемпотентным между ретраями
            resolve_response = await users_client.resolve_user(
                users_http_client,
                str(data.email),
                idempotency_key,
            )
            resolved = UserResolveResponse.model_validate(resolve_response)
            user = resolved.user
            resolved_user_created = resolved.created

        await saga_repository.mark_user_resolved(
            saga=saga,
            user_id=user.id,
            user_created=resolved_user_created,
        )
        # Фиксируем этап резолва пользователя отдельно от создания заказа
        await session.commit()
    except (
        UsersServiceUnavailableError,
        UsersServiceError,
        DownstreamUserNotFoundError,
        ValidationError,
        SQLAlchemyError,
    ):
        await _mark_saga_after_user_resolution_failure(session, saga_repository, idempotency_key)
        raise
    except Exception:
        # Прочие ошибки при резолве — помечаем сагу failed и пробрасываем дальше
        await _mark_saga_after_user_resolution_failure(session, saga_repository, idempotency_key)
        logger.exception("unexpected user resolution failure idempotency_key=%s", idempotency_key)
        raise

    return user


async def _create_order_and_finalize_step(
    session: AsyncSession,
    saga_repository: OrderCreationSagaRepository,
    saga: OrderCreationSagaModel,
    data: OrderCreate,
    user: UserRead,
    idempotency_key: str,
) -> OrderUser:
    try:
        order_data = data.model_copy(update={"user_id": user.id, "email": None})
        order = await orders_repo.create_order(session, order_data)
        response = OrderUser(
            order=OrderRead.model_validate(order),
            user=user,
        )
        await saga_repository.mark_order_created(
            saga=saga,
            order_id=order.id,
            response_body=response.model_dump(mode="json"),
        )
        # Конечное состояние саги фиксируем вместе с ответом для replay
        await session.commit()
    except (SQLAlchemyError, ValueError) as exc:
        # Ошибки БД и инвариантов репозитория (например user_id не задан)
        await session.rollback()
        logger.warning(
            "order creation failed idempotency_key=%s",
            idempotency_key,
            exc_info=exc,
        )
        await _persist_order_failure(saga_repository, idempotency_key)
        raise
    except Exception as exc:
        # Неожиданные ошибки (не БД / не инвариант репозитория) — тот же путь фиксации саги
        await session.rollback()
        logger.exception(
            "unexpected order creation failure idempotency_key=%s",
            idempotency_key,
            exc_info=exc,
        )
        await _persist_order_failure(saga_repository, idempotency_key)
        raise

    logger.info("order created order_id=%s idempotency_key=%s", order.id, idempotency_key)
    return response


async def _persist_order_failure(
    saga_repository: OrderCreationSagaRepository,
    idempotency_key: str,
) -> None:
    # Вспомогательная логика: после сбоя создания заказа перевести сагу в failed или compensation_pending
    saga = await saga_repository.get_by_key(idempotency_key)
    if not saga:
        return
    try:
        # Компенсация допустима только для пользователя, созданного этой сагой
        if saga.resolved_user_created and saga.resolved_user_id is not None:
            await saga_repository.mark_compensation_pending(
                saga=saga,
                error="order creation failed",
            )
        else:
            await saga_repository.mark_failed(
                saga=saga,
                error_code="order_creation_failed",
                error_message="Order creation failed",
            )
        await saga_repository.session.commit()
    except Exception:
        await saga_repository.session.rollback()
        # Воркер потом обработает этот случай
        logger.exception(
            "failed to persist failure state idempotency_key=%s",
            idempotency_key,
        )


async def get_order_enriched(
    session: AsyncSession,
    users_http_client: httpx.AsyncClient,
    order_id: UUID,
) -> OrderUser:
    order = await orders_repo.get_order_with_items(session, order_id)
    if not order:
        raise OrderNotFoundError(str(order_id))

    user_data = await users_client.get_user(users_http_client, order.user_id)
    user = UserRead.model_validate(user_data)

    return OrderUser(
        order=OrderRead.model_validate(order),
        user=user,
    )


async def create_order(
    session: AsyncSession,
    users_http_client: httpx.AsyncClient,
    data: OrderCreate,
    idempotency_key: str,
) -> OrderUser:
    saga_repository = OrderCreationSagaRepository(session)
    request_fingerprint = _build_request_fingerprint(data)

    replay = await _try_replay_existing_saga(
        saga_repository,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if replay is not None:
        return replay

    await saga_repository.create_or_get(
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        email=str(data.email) if data.email is not None else None,
    )
    # Фиксируем состояние начала саги
    await session.commit()

    saga_or_response = await _reload_saga_after_first_commit(
        saga_repository,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if isinstance(saga_or_response, OrderUser):
        return saga_or_response
    saga = saga_or_response

    # Резолв пользователя и фиксация checkpoint в саге
    user = await _resolve_user_step(
        session,
        users_http_client,
        saga_repository,
        saga,
        data,
        idempotency_key,
    )

    saga = await saga_repository.get_by_key(idempotency_key)
    if not saga:
        raise SagaInvariantError("saga missing after user resolution")

    # Создание заказа и финализация саги/ответа для replay
    return await _create_order_and_finalize_step(
        session,
        saga_repository,
        saga,
        data,
        user,
        idempotency_key,
    )
