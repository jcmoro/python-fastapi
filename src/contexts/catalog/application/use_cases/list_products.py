from contexts.catalog.application.dtos import ListProductsQuery, ProductDTO
from contexts.catalog.domain.ports.product_repository import ProductRepository


class ListProducts:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(self, query: ListProductsQuery) -> list[ProductDTO]:
        products = await self._repository.list(limit=query.limit, offset=query.offset)
        return [ProductDTO.from_entity(p) for p in products]
