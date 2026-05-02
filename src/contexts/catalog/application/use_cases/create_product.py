from contexts.catalog.application.dtos import CreateProductCommand, ProductDTO
from contexts.catalog.domain.exceptions import DuplicateSkuError
from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product


class CreateProduct:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(self, command: CreateProductCommand) -> ProductDTO:
        if await self._repository.exists_sku(command.sku):
            raise DuplicateSkuError(f"product with sku '{command.sku}' already exists")

        product = Product.create(
            sku=command.sku,
            name=command.name,
            price_cents=command.price_cents,
            currency=command.currency,
        )
        await self._repository.add(product)
        return ProductDTO.from_entity(product)
