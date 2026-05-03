from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from main import create_app
from sqlalchemy.ext.asyncio import AsyncSession

from contexts.catalog.domain.product import Product
from contexts.catalog.infrastructure.persistence.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from shared.infrastructure.database import get_session


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> FastAPI:
    """FastAPI app whose ``get_session`` dependency yields the test's transactional session."""
    application = create_app()

    async def get_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = get_session_override
    return application


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def add_product(
    db_session: AsyncSession,
    make_product: Callable[..., Product],
) -> Callable[..., Awaitable[Product]]:
    """Factory that persists a Product via the real adapter on the test session."""
    repository = SqlAlchemyProductRepository(db_session)

    async def _add(**kwargs: Any) -> Product:
        product = make_product(**kwargs)
        await repository.add(product)
        return product

    return _add


@pytest_asyncio.fixture
async def seeded_products(
    add_product: Callable[..., Awaitable[Product]],
) -> list[Product]:
    """Five persisted products in creation order. For list/pagination tests."""
    return [await add_product() for _ in range(5)]
