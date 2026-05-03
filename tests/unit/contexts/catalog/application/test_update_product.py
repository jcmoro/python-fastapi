from collections.abc import Callable
from uuid import uuid4

import pytest

from contexts.catalog.application.dtos import UpdateProductCommand
from contexts.catalog.application.use_cases.update_product import UpdateProduct
from contexts.catalog.domain.exceptions import InvalidProductError, ProductNotFoundError
from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product


@pytest.fixture
def use_case(repository: ProductRepository) -> UpdateProduct:
    return UpdateProduct(repository)


class TestExecute:
    async def test_updates_provided_fields(
        self,
        use_case: UpdateProduct,
        repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product(sku="SKU-1", name="Widget", price_cents=100)
        await repository.add(product)

        result = await use_case.execute(
            UpdateProductCommand(product_id=product.id, name="Gadget", price_cents=500)
        )

        assert result.name == "Gadget"
        assert result.price_cents == 500
        assert result.sku == "SKU-1"  # untouched
        stored = await repository.get(product.id)
        assert stored is not None
        assert stored.name == "Gadget"

    async def test_raises_when_product_does_not_exist(
        self, use_case: UpdateProduct
    ) -> None:
        missing_id = uuid4()

        with pytest.raises(ProductNotFoundError, match=str(missing_id)):
            await use_case.execute(UpdateProductCommand(product_id=missing_id, name="X"))

    async def test_propagates_domain_invariant_errors(
        self,
        use_case: UpdateProduct,
        repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product()
        await repository.add(product)

        with pytest.raises(InvalidProductError, match="price_cents"):
            await use_case.execute(
                UpdateProductCommand(product_id=product.id, price_cents=-1)
            )
