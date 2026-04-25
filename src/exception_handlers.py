import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.exceptions import (
    DownstreamUserNotFoundError,
    IdempotencyConflictError,
    IdempotencyFailedError,
    IdempotencyInProgressError,
    OrderNotFoundError,
    UsersServiceError,
    UsersServiceUnavailableError,
)
from src.request_context import request_id_var

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_safe(item) for item in value)
    return value


def _error_content(
    request: Request,
    details: Any,
) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", None) or request_id_var.get() or ""
    return {"request_id": request_id, "details": details}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        logger.exception(
            "sqlalchemy error method=%s path=%s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_content(
                request,
                "database error",
            ),
        )

    @app.exception_handler(OrderNotFoundError)
    async def order_not_found_handler(
        request: Request,
        exc: OrderNotFoundError,
    ) -> JSONResponse:
        logger.warning("order not found order_id=%s", exc.order_id)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_error_content(
                request,
                "Order not found",
            ),
        )

    @app.exception_handler(DownstreamUserNotFoundError)
    async def downstream_user_not_found_handler(
        request: Request,
        exc: DownstreamUserNotFoundError,
    ) -> JSONResponse:
        logger.warning("downstream user not found user_id=%s", exc.user_id)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_error_content(
                request,
                "User not found",
            ),
        )

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_handler(
        request: Request,
        exc: IdempotencyConflictError,
    ) -> JSONResponse:
        logger.warning("idempotency conflict key=%s", exc.key)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_content(
                request,
                "Idempotency key reused with different payload",
            ),
        )

    @app.exception_handler(IdempotencyInProgressError)
    async def idempotency_in_progress_handler(
        request: Request,
        exc: IdempotencyInProgressError,
    ) -> JSONResponse:
        logger.warning("idempotency key in progress key=%s", exc.key)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_content(
                request,
                "Order creation already in progress for this key",
            ),
        )

    @app.exception_handler(IdempotencyFailedError)
    async def idempotency_failed_handler(
        request: Request,
        exc: IdempotencyFailedError,
    ) -> JSONResponse:
        logger.warning("idempotency key failed key=%s", exc.key)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_content(
                request,
                exc.reason or "Order creation failed for this key",
            ),
        )

    @app.exception_handler(UsersServiceUnavailableError)
    async def users_unavailable_handler(
        request: Request,
        exc: UsersServiceUnavailableError,
    ) -> JSONResponse:
        logger.error("users service unavailable")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_error_content(
                request,
                "Users service unavailable",
            ),
        )

    @app.exception_handler(UsersServiceError)
    async def users_error_handler(
        request: Request,
        exc: UsersServiceError,
    ) -> JSONResponse:
        logger.error("users service returned error")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=_error_content(
                request,
                "Users service error",
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_content(
                request,
                _json_safe(exc.errors()),
            ),
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_handler(
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_content(
                request,
                _json_safe(exc.errors()),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "unhandled exception method=%s path=%s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_content(
                request,
                "Internal server error",
            ),
        )
