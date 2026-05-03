import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.infrastructure.persistence.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)


@pytest_asyncio.fixture
async def product_repository(db_session: AsyncSession) -> ProductRepository:
    return SqlAlchemyProductRepository(db_session)
