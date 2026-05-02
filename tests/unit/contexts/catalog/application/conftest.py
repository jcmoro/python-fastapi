from uuid import UUID

import pytest

from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product


class FakeProductRepository(ProductRepository):
    """In-memory ProductRepository for unit tests. Mocks at the port boundary."""

    def __init__(self) -> None:
        self._items: dict[UUID, Product] = {}

    async def add(self, product: Product) -> None:
        self._items[product.id] = product

    async def get(self, product_id: UUID) -> Product | None:
        return self._items.get(product_id)

    async def list(self, *, limit: int, offset: int) -> list[Product]:
        ordered = sorted(self._items.values(), key=lambda p: p.created_at)
        return ordered[offset : offset + limit]

    async def update(self, product: Product) -> None:
        self._items[product.id] = product

    async def delete(self, product_id: UUID) -> None:
        self._items.pop(product_id, None)

    async def exists_sku(self, sku: str) -> bool:
        return any(p.sku == sku for p in self._items.values())


@pytest.fixture
def repository() -> FakeProductRepository:
    return FakeProductRepository()
