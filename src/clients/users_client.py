import logging
from datetime import timedelta
from uuid import UUID

import httpx
from aiobreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerListener
from fastapi import HTTPException
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from src.config import Settings
from src.schemas.orders import UserRead

logger = logging.getLogger(__name__)
settings = Settings()

_http_client: httpx.AsyncClient | None = None


def init_http_client() -> None:
    global _http_client
    _http_client = httpx.AsyncClient(
        base_url=settings.users_service_url,
        timeout=5.0,
    )


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


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
    fail_max=5,
    timeout_duration=timedelta(seconds=30),
    exclude=[
        lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500
    ],
    listeners=[_StateLogger()],
    name="users-service",
)


@users_breaker
@retry(
    retry=retry_if_exception_type(httpx.TransportError),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, exp_base=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _fetch_user(user_id: UUID) -> dict:
    response = await _http_client.get(f"/users/{user_id}")
    response.raise_for_status()
    return response.json()


async def get_user(user_id: UUID) -> UserRead:
    try:
        data = await _fetch_user(user_id)
    except CircuitBreakerError:
        logger.error("Circuit breaker open for '%s', rejecting request", users_breaker.name)
        raise HTTPException(status_code=503, detail="Users service unavailable")
    except httpx.TransportError as exc:
        logger.error("Transport error reaching users service after retries: %s", exc)
        raise HTTPException(status_code=503, detail="Users service unavailable")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="User not found")
        raise HTTPException(status_code=502, detail="Users service error")
    return UserRead(**data)
