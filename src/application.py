import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from src.clients.users_client import close_http_client, create_http_client
from src.exceptions.exception_handlers import register_exception_handlers
from src.logging_filters import RequestIdLogFilter
from src.middleware.request_id import register_request_id_middleware
from src.routers.orders import router as orders_router


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "[request_id=%(request_id)s] %(message)s"
        ),
    )
    request_id_filter = RequestIdLogFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(request_id_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.users_http_client = create_http_client()
    yield
    await close_http_client(app.state.users_http_client)


def get_app() -> FastAPI:
    app = FastAPI(
        docs_url='/docs',
        openapi_url='/openapi.json',
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    register_request_id_middleware(app=app)

    register_exception_handlers(app)
    app.include_router(orders_router)

    return app
