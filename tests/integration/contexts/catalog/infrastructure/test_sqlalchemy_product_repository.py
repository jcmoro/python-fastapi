from collections.abc import Callable
from uuid import uuid4

from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product


class TestAddAndGet:
    async def test_round_trip(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product(sku="SKU-1", name="Widget", price_cents=999)

        await product_repository.add(product)
        loaded = await product_repository.get(product.id)

        assert loaded is not None
        assert loaded.id == product.id
        assert loaded.sku == "SKU-1"
        assert loaded.name == "Widget"
        assert loaded.price_cents == 999
        assert loaded.currency == "EUR"

    async def test_get_returns_none_when_missing(
        self, product_repository: ProductRepository
    ) -> None:
        assert await product_repository.get(uuid4()) is None


class TestExistsSku:
    async def test_returns_true_after_add(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        await product_repository.add(make_product(sku="SKU-EXISTS"))

        assert await product_repository.exists_sku("SKU-EXISTS") is True

    async def test_returns_false_when_missing(
        self, product_repository: ProductRepository
    ) -> None:
        assert await product_repository.exists_sku("NOT-THERE") is False


class TestList:
    async def test_returns_paginated_results_ordered_by_created_at(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        products = [make_product() for _ in range(5)]
        for product in products:
            await product_repository.add(product)

        first_page = await product_repository.list(limit=2, offset=0)
        second_page = await product_repository.list(limit=2, offset=2)

        assert [p.id for p in first_page] == [p.id for p in products[:2]]
        assert [p.id for p in second_page] == [p.id for p in products[2:4]]

    async def test_empty_when_no_rows(
        self, product_repository: ProductRepository
    ) -> None:
        assert await product_repository.list(limit=10, offset=0) == []


class TestUpdate:
    async def test_persists_changes(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product(sku="SKU-1", name="Widget", price_cents=100)
        await product_repository.add(product)

        updated = product.with_changes(name="Gadget", price_cents=500)
        await product_repository.update(updated)

        loaded = await product_repository.get(product.id)
        assert loaded is not None
        assert loaded.name == "Gadget"
        assert loaded.price_cents == 500

    async def test_silently_ignores_missing_product(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        ghost = make_product()

        await product_repository.update(ghost)  # must not raise

        assert await product_repository.get(ghost.id) is None


class TestDelete:
    async def test_removes_existing_product(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product()
        await product_repository.add(product)

        await product_repository.delete(product.id)

        assert await product_repository.get(product.id) is None

    async def test_silently_ignores_missing_product(
        self, product_repository: ProductRepository
    ) -> None:
        await product_repository.delete(uuid4())  # must not raise
