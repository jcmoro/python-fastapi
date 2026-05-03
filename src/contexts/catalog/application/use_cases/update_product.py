from contexts.catalog.application.dtos import ProductDTO, UpdateProductCommand
from contexts.catalog.domain.exceptions import ProductNotFoundError
from contexts.catalog.domain.ports.product_repository import ProductRepository


class UpdateProduct:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(self, command: UpdateProductCommand) -> ProductDTO:
        product = await self._repository.get(command.product_id)
        if product is None:
            raise ProductNotFoundError(f"product '{command.product_id}' not found")

        updated = product.with_changes(
            name=command.name,
            price_cents=command.price_cents,
            currency=command.currency,
        )
        await self._repository.update(updated)
        return ProductDTO.from_entity(updated)
