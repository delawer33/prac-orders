from uuid import uuid4

from fastapi import FastAPI, Request, Response

from src.request_context import request_id_var


HEADER_NAME = "X-Request-ID"


def register_request_id_middleware(*, app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        raw = request.headers.get(HEADER_NAME)
        request_id = raw.strip() if raw else str(uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers.setdefault(HEADER_NAME, request_id)
        return response
