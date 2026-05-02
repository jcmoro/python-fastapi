from abc import ABC, abstractmethod
from uuid import UUID

from contexts.catalog.domain.product import Product


class ProductRepository(ABC):
    @abstractmethod
    async def add(self, product: Product) -> None: ...

    @abstractmethod
    async def get(self, product_id: UUID) -> Product | None: ...

    @abstractmethod
    async def list(self, *, limit: int, offset: int) -> list[Product]: ...

    @abstractmethod
    async def update(self, product: Product) -> None: ...

    @abstractmethod
    async def delete(self, product_id: UUID) -> None: ...

    @abstractmethod
    async def exists_sku(self, sku: str) -> bool: ...
