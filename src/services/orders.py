import hashlib
import json
import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.users_client import UsersGateway
from src.exceptions import (
    DownstreamUserNotFoundError,
    IdempotencyConflictError,
    IdempotencyFailedError,
    IdempotencyInProgressError,
    InvariantViolationError,
    OrderNotFoundError,
    SagaInvariantError,
    UsersServiceError,
    UsersServiceUnavailableError,
)
from src.models.order_creation_sagas import OrderCreationSagaModel, OrderCreationSagaStatus
from src.repositories.order_creation_sagas import OrderCreationSagaRepository
from src.repositories.orders import OrdersRepository
from src.schemas.orders import OrderCreate, OrderRead, OrderUser, UserRead, UserResolveResponse

logger = logging.getLogger(__name__)


class OrdersService:
    def __init__(
        self,
        repo: OrdersRepository,
        saga_repo: OrderCreationSagaRepository,
    ) -> None:
        if saga_repo.session is not repo.db:
            raise InvariantViolationError(
                "OrderCreationSagaRepository must use the same AsyncSession as OrdersRepository"
            )
        self.repo = repo
        self.saga_repo = saga_repo

    @property
    def db(self) -> AsyncSession:
        return self.repo.db

    @staticmethod
    def _build_request_fingerprint(data: OrderCreate) -> str:
        payload = data.model_dump(mode="json", exclude_none=True)
        raw_value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()

    @staticmethod
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
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> OrderUser | None:
        # Уже есть сага по ключу — отдаём сохранённый результат или ошибку идемпотентности
        existing_saga = await self.saga_repo.get_by_key(idempotency_key)
        if not existing_saga:
            return None
        return self._resolve_replay_from_saga(
            existing_saga,
            request_fingerprint=request_fingerprint,
        )

    async def _reload_saga_after_first_commit(
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> OrderUser | OrderCreationSagaModel:
        saga = await self.saga_repo.get_by_key(idempotency_key)
        if not saga:
            raise SagaInvariantError("saga missing after upsert")
        # Параллельный запрос мог продвинуть сагу — отдаём тот же ответ, что и при повторе ключа
        if saga.status != OrderCreationSagaStatus.STARTED:
            return self._resolve_replay_from_saga(saga, request_fingerprint=request_fingerprint)
        return saga

    async def _mark_saga_after_user_resolution_failure(
        self,
        idempotency_key: str,
    ) -> None:
        await self.db.rollback()
        saga = await self.saga_repo.get_by_key(idempotency_key)
        if saga:
            # Не удалось достучаться до users / валидация — финализируем сагу как ошибочную
            await self.saga_repo.mark_failed(
                saga=saga,
                error_code="user_resolution_failed",
                error_message="User resolution failed",
            )
            await self.db.commit()

    async def _resolve_user_step(
        self,
        users: UsersGateway,
        saga: OrderCreationSagaModel,
        data: OrderCreate,
        idempotency_key: str,
    ) -> UserRead:
        try:
            if data.user_id is not None:
                user_data = await users.get_user(data.user_id)
                user = UserRead.model_validate(user_data)
                resolved_user_created = False
            else:
                # external_request_id == idempotency_key делает резолв пользователя
                # идемпотентным между ретраями
                resolve_response = await users.resolve_user(
                    str(data.email),
                    idempotency_key,
                )
                resolved = UserResolveResponse.model_validate(resolve_response)
                user = resolved.user
                resolved_user_created = resolved.created

            await self.saga_repo.mark_user_resolved(
                saga=saga,
                user_id=user.id,
                user_created=resolved_user_created,
            )
            # Фиксируем этап резолва пользователя отдельно от создания заказа
            await self.db.commit()
        except Exception:
            # Прочие ошибки при резолве — помечаем сагу failed и пробрасываем дальше
            await self._mark_saga_after_user_resolution_failure(idempotency_key)
            raise

        return user

    async def _create_order_and_finalize_step(
        self,
        saga: OrderCreationSagaModel,
        data: OrderCreate,
        user: UserRead,
        idempotency_key: str,
    ) -> OrderUser:
        try:
            order_data = data.model_copy(update={"user_id": user.id, "email": None})
            order = await self.repo.create_order(order_data)
            response = OrderUser(
                order=OrderRead.model_validate(order),
                user=user,
            )
            await self.saga_repo.mark_order_created(
                saga=saga,
                order_id=order.id,
                response_body=response.model_dump(mode="json"),
            )
            # Конечное состояние саги фиксируем вместе с ответом для replay
            await self.db.commit()
        except SQLAlchemyError:
            # Ошибки БД и инвариантов репозитория (например user_id не задан)
            await self.db.rollback()
            await self._persist_order_failure(idempotency_key)
            raise
        except Exception:
            # Неожиданные ошибки (не БД / не инвариант репозитория) — тот же путь фиксации саги
            await self.db.rollback()
            await self._persist_order_failure(idempotency_key)
            raise

        logger.info("order created order_id=%s idempotency_key=%s", order.id, idempotency_key)
        return response

    async def _persist_order_failure(
        self,
        idempotency_key: str,
    ) -> None:
        # Вспомогательная логика: после сбоя создания заказа перевести сагу в failed или compensation_pending
        saga = await self.saga_repo.get_by_key(idempotency_key)
        if not saga:
            return
        try:
            # Компенсация допустима только для пользователя, созданного этой сагой
            if saga.resolved_user_created and saga.resolved_user_id is not None:
                await self.saga_repo.mark_compensation_pending(
                    saga=saga,
                    error="order creation failed",
                )
            else:
                await self.saga_repo.mark_failed(
                    saga=saga,
                    error_code="order_creation_failed",
                    error_message="Order creation failed",
                )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            # Воркер потом обработает этот случай
            logger.exception(
                "failed to persist failure state idempotency_key=%s",
                idempotency_key,
            )

    async def get_order_enriched(
        self,
        users: UsersGateway,
        order_id: UUID,
    ) -> OrderUser:
        order = await self.repo.get_order_with_items(order_id)
        if not order:
            raise OrderNotFoundError(str(order_id))

        user_data = await users.get_user(order.user_id)
        user = UserRead.model_validate(user_data)

        return OrderUser(
            order=OrderRead.model_validate(order),
            user=user,
        )

    async def create_order(
        self,
        users: UsersGateway,
        data: OrderCreate,
        idempotency_key: str,
    ) -> OrderUser:
        request_fingerprint = self._build_request_fingerprint(data)

        replay = await self._try_replay_existing_saga(
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if replay is not None:
            return replay

        await self.saga_repo.upsert(
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            email=str(data.email) if data.email is not None else None,
        )
        # Фиксируем состояние начала саги
        await self.db.commit()

        saga_or_response = await self._reload_saga_after_first_commit(
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if isinstance(saga_or_response, OrderUser):
            return saga_or_response
        saga = saga_or_response

        # Резолв пользователя и фиксация checkpoint в саге
        user = await self._resolve_user_step(
            users,
            saga,
            data,
            idempotency_key,
        )

        saga = await self.saga_repo.get_by_key(idempotency_key)
        if not saga:
            raise SagaInvariantError("saga missing after user resolution")

        # Создание заказа и финализация саги/ответа для replay
        return await self._create_order_and_finalize_step(
            saga,
            data,
            user,
            idempotency_key,
        )
