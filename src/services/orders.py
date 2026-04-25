import asyncio
import hashlib
import json
import logging
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients import users_client
from src.exceptions import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyKeyAlreadyExistsError,
    OrderNotFoundError,
)
from src.models.order_idempotency_keys import OrderIdempotencyKeyModel, OrderIdempotencyStatus
from src.repositories import order_idempotency_keys as idempotency_repo
from src.repositories import order_creation_sagas as saga_repo
from src.repositories import orders as orders_repo
from src.schemas.orders import OrderCreate, OrderRead, OrderUser, UserRead, UserResolveResponse

logger = logging.getLogger(__name__)


def _build_request_fingerprint(data: OrderCreate) -> str:
    payload = data.model_dump(mode="json", exclude_none=True)
    raw_value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def _resolve_idempotency_record(
    record: OrderIdempotencyKeyModel,
    *,
    request_fingerprint: str,
) -> OrderUser:
    if record.request_fingerprint != request_fingerprint:
        raise IdempotencyConflictError(record.key)
    # Возвращаем сохраненный ответ
    if record.status == OrderIdempotencyStatus.SUCCEEDED and record.response_body is not None:
        return OrderUser.model_validate(record.response_body)
    # Любой статус кроме SUCCEEDED для клиента считается незавершенным
    raise IdempotencyInProgressError(record.key)


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
    request_fingerprint = _build_request_fingerprint(data)
    idempotency_record: OrderIdempotencyKeyModel

    try:
        idempotency_record = await idempotency_repo.reserve_key(
            session=session,
            key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
    except IdempotencyKeyAlreadyExistsError:
        await session.rollback()
        existing_record = await idempotency_repo.get_key(session, idempotency_key)
        if not existing_record:
            raise
        if existing_record.request_fingerprint != request_fingerprint:
            raise IdempotencyConflictError(idempotency_key)
        if existing_record.status == OrderIdempotencyStatus.FAILED:
            # Если статус FAILED, то пробуем выполнить логику снова
            # Для этого явно удаляем запись и заново резервируем ключ,
            # чтобы переоткрыть обработку в рамках той же idempotency
            await idempotency_repo.delete_key(session, existing_record)
            try:
                idempotency_record = await idempotency_repo.reserve_key(
                    session=session,
                    key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                )
            except IdempotencyKeyAlreadyExistsError:
                # Если другой запрос уже пересоздал этот ключ
                existing_record = await idempotency_repo.get_key(session, idempotency_key)
                if not existing_record:
                    raise
                return _resolve_idempotency_record(
                    existing_record,
                    request_fingerprint=request_fingerprint,
                )
        else:
            # Для PROCESSING/SUCCEEDED ответ определяется по сохраненному состоянию ключа
            return _resolve_idempotency_record(
                existing_record,
                request_fingerprint=request_fingerprint,
            )

    saga = await saga_repo.create_or_get(
        session=session,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        email=str(data.email) if data.email is not None else None,
    )
    # Сначала фиксируем состояние начала саги, затем внешние сайд-эффекты
    await session.commit()
    resolved_user_created = False
    resolved_user_id: UUID | None = None
    user: UserRead

    try:
        if data.user_id is not None:
            user_data = await users_client.get_user(users_http_client, data.user_id)
            user = UserRead.model_validate(user_data)
            resolved_user_id = user.id
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
            resolved_user_id = resolved.user.id

        await saga_repo.mark_user_created(
            session=session,
            saga=saga,
            user_id=user.id,
            user_created=resolved_user_created,
        )
        # Фиксируем этап резолва пользователя отдельно от создания заказ
        await session.commit()
    except Exception as exc:
        await session.rollback()
        saga = await saga_repo.get_by_key(session, idempotency_key)
        if not saga:
            raise
        await saga_repo.mark_failed(
            session=session,
            saga=saga,
            error=f"user resolution failed: {exc}",
        )
        # Если пользователя резолвить не удалось — эта сага завершена с FAILED
        await idempotency_repo.mark_key_failed(
            session=session,
            record=idempotency_record,
            error_code="user_resolution_failed",
            error_message=f"User resolution failed: {exc}",
        )
        await session.commit()
        raise

    try:
        order_data = data.model_copy(update={"user_id": user.id, "email": None})
        order = await orders_repo.create_order(session, order_data)
        response = OrderUser(
            order=OrderRead.model_validate(order),
            user=user,
        )
        await idempotency_repo.complete_key(
            session=session,
            record=idempotency_record,
            order_id=order.id,
            response_body=response.model_dump(mode="json"),
        )
        # Конечные состояния саги и idempotency фиксируем в одной транзакции
        await saga_repo.mark_order_created(
            session=session,
            saga=saga,
            order_id=order.id,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        saga = await saga_repo.get_by_key(session, idempotency_key)
        if not saga:
            raise
        try:
            if resolved_user_created and resolved_user_id is not None:
                # Компенсация допустима только для пользователя, созданного этой сагой
                await saga_repo.mark_compensation_pending(
                    session=session,
                    saga=saga,
                    error=f"order creation failed: {exc}",
                )
            else:
                # Существующего пользователя удалять нельзя, поэтому FAILED без компенсации
                await saga_repo.mark_failed(
                    session=session,
                    saga=saga,
                    error=f"order creation failed without compensatable user: {exc}",
                )
                await idempotency_repo.mark_key_failed(
                    session=session,
                    record=idempotency_record,
                    error_code="order_creation_failed",
                    error_message=f"Order creation failed: {exc}",
                )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "failed to persist failure state idempotency_key=%s user_id=%s",
                idempotency_key,
                resolved_user_id,
            )
        raise

    logger.info("order created order_id=%s idempotency_key=%s", order.id, idempotency_key)
    return response
