import logging
from datetime import timedelta
from typing import Annotated, Any, Dict
from uuid import UUID

import httpx
from aiobreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerListener
from fastapi import Depends, Request
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from src.config import Settings
from src.exceptions import DownstreamUserNotFoundError, UsersServiceError, UsersServiceUnavailableError
logger = logging.getLogger(__name__)
settings = Settings()
USERS_API_PREFIX = settings.users_service_api_prefix


def create_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.users_service_url,
        timeout=settings.users_service_http_timeout_seconds,
    )


async def close_http_client(client: httpx.AsyncClient) -> None:
    await client.aclose()


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.users_http_client


UsersHttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


class _StateLogger(CircuitBreakerListener):
    def state_change(self, breaker, old, new) -> None:
        logger.warning(
            "Circuit breaker '%s' state change: %s -> %s",
            breaker.name,
            old.state.value,
            new.state.value,
        )

    def failure(self, breaker, exception) -> None:
        logger.error(
            "Circuit breaker '%s' recorded failure (%d/%d): %s",
            breaker.name,
            breaker.fail_counter,
            breaker.fail_max,
            exception,
        )


users_breaker = CircuitBreaker(
    fail_max=settings.users_service_cb_fail_max,
    timeout_duration=timedelta(seconds=settings.users_service_cb_timeout_seconds),
    exclude=[
        lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500
    ],
    listeners=[_StateLogger()],
    name=settings.users_service_cb_name,
)


def _is_retryable_exception(exception: BaseException) -> bool:
    if isinstance(exception, httpx.TransportError):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        return status_code in {408, 429} or 500 <= status_code < 600
    return False


@users_breaker
@retry(
    retry=retry_if_exception(_is_retryable_exception),
    stop=stop_after_attempt(settings.users_service_retry_attempts),
    wait=wait_exponential_jitter(
        initial=settings.users_service_retry_wait_initial_seconds,
        exp_base=settings.users_service_retry_wait_exp_base,
        max=settings.users_service_retry_wait_max_seconds,
    ),
    before_sleep=before_sleep_log(logger, logging.DEBUG),
    reraise=True,
)
async def _fetch_user(client: httpx.AsyncClient, user_id: UUID) -> Dict[str, Any]:
    response = await client.get(f"{USERS_API_PREFIX}/{user_id}")
    # оставляю raise_for status, т.к. фукнция вспомогательная
    # и обработка httpx ошибок происходит ниже в фукнции get_user()
    response.raise_for_status()
    return response.json()


@users_breaker
@retry(
    retry=retry_if_exception(_is_retryable_exception),
    stop=stop_after_attempt(settings.users_service_retry_attempts),
    wait=wait_exponential_jitter(
        initial=settings.users_service_retry_wait_initial_seconds,
        exp_base=settings.users_service_retry_wait_exp_base,
        max=settings.users_service_retry_wait_max_seconds,
    ),
    before_sleep=before_sleep_log(logger, logging.DEBUG),
    reraise=True,
)
async def _resolve_user(client: httpx.AsyncClient, email: str, external_request_id: str) -> Dict[str, Any]:
    response = await client.post(
        f"{USERS_API_PREFIX}/resolve",
        json={"email": email, "external_request_id": external_request_id},
    )
    # оставляю raise_for status, т.к. фукнция вспомогательная
    # и обработка httpx ошибок происходит ниже в фукнции resolve_user()
    response.raise_for_status()
    return response.json()


@users_breaker
@retry(
    retry=retry_if_exception(_is_retryable_exception),
    stop=stop_after_attempt(settings.users_service_retry_attempts),
    wait=wait_exponential_jitter(
        initial=settings.users_service_retry_wait_initial_seconds,
        exp_base=settings.users_service_retry_wait_exp_base,
        max=settings.users_service_retry_wait_max_seconds,
    ),
    before_sleep=before_sleep_log(logger, logging.DEBUG),
    reraise=True,
)
async def _cancel_user_for_order_saga(client: httpx.AsyncClient, user_id: UUID) -> None:
    response = await client.post(f"{USERS_API_PREFIX}/{user_id}/saga-cancellation")
    if response.status_code not in {204, 404}:
        # оставляю raise_for status, т.к. фукнция вспомогательная
        # и обработка httpx ошибок происходит ниже в фукнции cancel_user_for_order_saga()
        response.raise_for_status()


async def get_user(client: httpx.AsyncClient, user_id: UUID) -> Dict[str, Any]:
    try:
        data = await _fetch_user(client, user_id)
    except CircuitBreakerError:
        err = UsersServiceUnavailableError()
        err.log_detail = f"circuit breaker '{users_breaker.name}' open"
        raise err
    except httpx.TransportError as exc:
        err = UsersServiceUnavailableError()
        err.log_detail = f"transport error after retries: {exc}"
        raise err from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise DownstreamUserNotFoundError(str(user_id)) from exc
        err = UsersServiceError()
        err.log_detail = f"http {exc.response.status_code} from users service"
        raise err from exc
    return data


async def resolve_user(client: httpx.AsyncClient, email: str, external_request_id: str) -> Dict[str, Any]:
    try:
        data = await _resolve_user(client, email, external_request_id)
    except CircuitBreakerError:
        err = UsersServiceUnavailableError()
        err.log_detail = f"circuit breaker '{users_breaker.name}' open"
        raise err
    except httpx.TransportError as exc:
        err = UsersServiceUnavailableError()
        err.log_detail = f"transport error after retries: {exc}"
        raise err from exc
    except httpx.HTTPStatusError as exc:
        err = UsersServiceError()
        err.log_detail = f"http {exc.response.status_code} from users service"
        raise err from exc
    return data


async def cancel_user_for_order_saga(client: httpx.AsyncClient, user_id: UUID) -> None:
    """Мягкая отмена пользователя для компенсации саги orders (без физического удаления)."""
    try:
        await _cancel_user_for_order_saga(client, user_id)
    except CircuitBreakerError:
        err = UsersServiceUnavailableError()
        err.log_detail = f"circuit breaker '{users_breaker.name}' open"
        raise err
    except httpx.TransportError as exc:
        err = UsersServiceUnavailableError()
        err.log_detail = f"transport error after retries: {exc}"
        raise err from exc
    except httpx.HTTPStatusError as exc:
        err = UsersServiceError()
        err.log_detail = (
            f"saga cancellation rejected (active user) user_id={user_id}"
            if exc.response.status_code == 409
            else f"http {exc.response.status_code} from users service"
        )
        raise err from exc
