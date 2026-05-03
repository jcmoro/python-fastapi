from uuid import UUID

from contexts.catalog.domain.exceptions import ProductNotFoundError
from contexts.catalog.domain.ports.product_repository import ProductRepository


class DeleteProduct:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(self, product_id: UUID) -> None:
        product = await self._repository.get(product_id)
        if product is None:
            raise ProductNotFoundError(f"product '{product_id}' not found")
        await self._repository.delete(product_id)
