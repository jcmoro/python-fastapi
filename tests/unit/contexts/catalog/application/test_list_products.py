from collections.abc import Callable

import pytest

from contexts.catalog.application.dtos import ListProductsQuery
from contexts.catalog.application.use_cases.list_products import ListProducts
from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product


@pytest.fixture
def use_case(repository: ProductRepository) -> ListProducts:
    return ListProducts(repository)


class TestExecute:
    async def test_returns_paginated_dtos(
        self,
        use_case: ListProducts,
        repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        seeded = [make_product() for _ in range(5)]
        for product in seeded:
            await repository.add(product)

        first_page = await use_case.execute(ListProductsQuery(limit=2, offset=0))
        second_page = await use_case.execute(ListProductsQuery(limit=2, offset=2))

        assert [d.id for d in first_page] == [p.id for p in seeded[:2]]
        assert [d.id for d in second_page] == [p.id for p in seeded[2:4]]

    async def test_returns_empty_when_no_rows(self, use_case: ListProducts) -> None:
        result = await use_case.execute(ListProductsQuery())

        assert result == []

    async def test_uses_default_limit_and_offset(
        self,
        use_case: ListProducts,
        repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product()
        await repository.add(product)

        result = await use_case.execute(ListProductsQuery())

        assert len(result) == 1
        assert result[0].id == product.id
