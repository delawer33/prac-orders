import logging
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import Settings

logger = logging.getLogger(__name__)

settings = Settings()

engine: AsyncEngine = create_async_engine(
    str(settings.postgres_url),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=5,
    pool_timeout=3,
    pool_recycle=1800,
    connect_args={
        "timeout": 5,
    },
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
