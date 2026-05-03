from collections.abc import Callable
from uuid import uuid4

import pytest

from contexts.catalog.application.dtos import ProductDTO
from contexts.catalog.application.use_cases.get_product import GetProduct
from contexts.catalog.domain.exceptions import ProductNotFoundError
from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product


@pytest.fixture
def use_case(repository: ProductRepository) -> GetProduct:
    return GetProduct(repository)


class TestExecute:
    async def test_returns_dto_when_product_exists(
        self,
        use_case: GetProduct,
        repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product(sku="SKU-1", name="Widget", price_cents=999)
        await repository.add(product)

        result = await use_case.execute(product.id)

        assert isinstance(result, ProductDTO)
        assert result.id == product.id
        assert result.sku == "SKU-1"

    async def test_raises_when_product_does_not_exist(self, use_case: GetProduct) -> None:
        missing_id = uuid4()

        with pytest.raises(ProductNotFoundError, match=str(missing_id)):
            await use_case.execute(missing_id)
