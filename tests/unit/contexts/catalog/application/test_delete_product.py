from collections.abc import Callable
from uuid import uuid4

import pytest

from contexts.catalog.application.use_cases.delete_product import DeleteProduct
from contexts.catalog.domain.exceptions import ProductNotFoundError
from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product


@pytest.fixture
def use_case(repository: ProductRepository) -> DeleteProduct:
    return DeleteProduct(repository)


class TestExecute:
    async def test_removes_existing_product(
        self,
        use_case: DeleteProduct,
        repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product()
        await repository.add(product)

        await use_case.execute(product.id)

        assert await repository.get(product.id) is None

    async def test_raises_when_product_does_not_exist(self, use_case: DeleteProduct) -> None:
        missing_id = uuid4()

        with pytest.raises(ProductNotFoundError, match=str(missing_id)):
            await use_case.execute(missing_id)
