import os
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.exceptions import DownstreamUserNotFoundError
from src.models import metadata

TEST_DB_URL = os.getenv("TEST_POSTGRES_URL", "postgresql+asyncpg://postgres:123456@localhost:5433/orders_test")


async def _make_session() -> AsyncGenerator[AsyncSession, None]:
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    session_maker = async_sessionmaker(eng, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    async with eng.begin() as conn:
        for table in reversed(metadata.sorted_tables):
            await conn.execute(sa.delete(table))
    await eng.dispose()


import pytest  # noqa: E402


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in _make_session():
        yield session


class FakeUsersGateway:
    def __init__(self, users: dict[str, dict[str, Any]] | None = None) -> None:
        self._users: dict[str, dict[str, Any]] = users or {}

    async def get_user(self, user_id: UUID) -> dict[str, Any]:
        user = self._users.get(str(user_id))
        if not user:
            raise DownstreamUserNotFoundError(str(user_id))
        return user

    async def resolve_user(self, email: str, external_request_id: str) -> dict[str, Any]:
        for user in self._users.values():
            if user.get("email") == email:
                return {"user": user, "created": False}
        raise DownstreamUserNotFoundError(email)

    async def cancel_user_for_order_saga(self, user_id: UUID) -> None:
        pass
