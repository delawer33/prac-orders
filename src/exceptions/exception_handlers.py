import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.exceptions import (
    AppError,
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
    @app.exception_handler(AppError)
    async def app_error_handler(
        request: Request,
        exc: AppError,
    ) -> JSONResponse:
        detail = exc.log_detail or str(exc) or None
        getattr(logger, exc.log_level)(
            "%s method=%s path=%s%s",
            type(exc).__name__,
            request.method,
            request.url.path,
            f" detail={detail!r}" if detail else "",
        )
        return JSONResponse(
            status_code=exc.http_status_code,
            content=_error_content(request, exc.public_message),
        )

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

