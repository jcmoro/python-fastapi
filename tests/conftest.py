from collections.abc import AsyncIterator, Callable, Iterator
from itertools import count

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from main import create_app
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from contexts.catalog.domain.product import Product
from shared.infrastructure.settings import get_settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Sync TestClient against the unmodified app. Used by tests that don't touch the DB."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def make_product() -> Callable[..., Product]:
    """Pure factory for valid Product entities. Auto-increments SKU per call to avoid collisions."""
    counter = count(1)

    def _factory(
        *,
        sku: str | None = None,
        name: str = "Test Widget",
        price_cents: int = 1000,
        currency: str = "EUR",
    ) -> Product:
        return Product.create(
            sku=sku or f"SKU-{next(counter)}",
            name=name,
            price_cents=price_cents,
            currency=currency,
        )

    return _factory


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().test_database_url, future=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Function-scoped session wrapped in a transaction that rolls back on teardown."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
