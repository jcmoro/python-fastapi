from collections.abc import Callable
from uuid import uuid4

from contexts.assistant.domain.catalog_product import CatalogProduct
from contexts.assistant.infrastructure.catalog.list_products_catalog_reader import (
    ListProductsCatalogReader,
)
from contexts.catalog.application.use_cases.get_product import GetProduct
from contexts.catalog.application.use_cases.list_products import ListProducts
from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product


class TestReadAll:
    async def test_reads_every_product_across_pages(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        products = [make_product() for _ in range(5)]
        for product in products:
            await product_repository.add(product)
        reader = ListProductsCatalogReader(
            ListProducts(product_repository), GetProduct(product_repository), page_size=2
        )

        result = await reader.read_all()

        assert sorted(p.product_id for p in result) == sorted(p.id for p in products)

    async def test_maps_product_fields(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        product = make_product(sku="SKU-MAP", name="Mapped", price_cents=1234, currency="USD")
        await product_repository.add(product)
        reader = ListProductsCatalogReader(
            ListProducts(product_repository), GetProduct(product_repository)
        )

        [result] = await reader.read_all()

        assert result == CatalogProduct(
            product_id=product.id,
            sku="SKU-MAP",
            name="Mapped",
            price_cents=1234,
            currency="USD",
        )

    async def test_empty_catalog_returns_no_products(
        self, product_repository: ProductRepository
    ) -> None:
        reader = ListProductsCatalogReader(
            ListProducts(product_repository), GetProduct(product_repository)
        )

        assert await reader.read_all() == []


class TestMissing:
    async def test_r1_reports_only_ids_not_in_the_catalog(
        self,
        product_repository: ProductRepository,
        make_product: Callable[..., Product],
    ) -> None:
        existing = make_product()
        await product_repository.add(existing)
        gone = uuid4()
        reader = ListProductsCatalogReader(
            ListProducts(product_repository), GetProduct(product_repository)
        )

        assert await reader.missing([existing.id, gone]) == [gone]
