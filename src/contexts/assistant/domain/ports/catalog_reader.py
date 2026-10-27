from abc import ABC, abstractmethod
from uuid import UUID

from contexts.assistant.domain.catalog_product import CatalogProduct


class CatalogReader(ABC):
    @abstractmethod
    async def read_all(self) -> list[CatalogProduct]:
        """Returns the products currently in the catalog, without duplicates. A product may be
        missing from the result even though it exists (paging is not snapshot-consistent), so
        absence from this list is not proof of deletion: use ``missing`` for that.
        """

    @abstractmethod
    async def missing(self, product_ids: list[UUID]) -> list[UUID]:
        """Returns the given ids that do not exist in the catalog, in the same order."""
