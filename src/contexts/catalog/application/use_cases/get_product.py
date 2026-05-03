from uuid import UUID

from contexts.catalog.application.dtos import ProductDTO
from contexts.catalog.domain.exceptions import ProductNotFoundError
from contexts.catalog.domain.ports.product_repository import ProductRepository


class GetProduct:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(self, product_id: UUID) -> ProductDTO:
        product = await self._repository.get(product_id)
        if product is None:
            raise ProductNotFoundError(f"product '{product_id}' not found")
        return ProductDTO.from_entity(product)
