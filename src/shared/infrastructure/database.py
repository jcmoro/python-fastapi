from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.infrastructure.settings import get_settings


def _create_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True, pool_pre_ping=True)


_settings = get_settings()
engine: AsyncEngine = _create_engine(_settings.database_url)
session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
