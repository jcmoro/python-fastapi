import pytest

from contexts.catalog.application.dtos import CreateProductCommand, ProductDTO
from contexts.catalog.application.use_cases.create_product import CreateProduct
from contexts.catalog.domain.exceptions import DuplicateSkuError, InvalidProductError
from contexts.catalog.domain.ports.product_repository import ProductRepository


@pytest.fixture
def use_case(repository: ProductRepository) -> CreateProduct:
    return CreateProduct(repository)


class TestExecute:
    async def test_returns_dto_with_persisted_fields(
        self, use_case: CreateProduct, repository: ProductRepository
    ) -> None:
        command = CreateProductCommand(sku="SKU-1", name="Widget", price_cents=999)

        result = await use_case.execute(command)

        assert isinstance(result, ProductDTO)
        assert result.sku == "SKU-1"
        assert result.name == "Widget"
        assert result.price_cents == 999
        assert result.currency == "EUR"
        stored = await repository.get(result.id)
        assert stored is not None
        assert stored.sku == "SKU-1"

    async def test_uses_provided_currency(self, use_case: CreateProduct) -> None:
        command = CreateProductCommand(
            sku="SKU-1", name="Widget", price_cents=999, currency="USD"
        )

        result = await use_case.execute(command)

        assert result.currency == "USD"

    async def test_raises_when_sku_already_exists(self, use_case: CreateProduct) -> None:
        await use_case.execute(CreateProductCommand(sku="SKU-1", name="A", price_cents=100))

        with pytest.raises(DuplicateSkuError, match="SKU-1"):
            await use_case.execute(
                CreateProductCommand(sku="SKU-1", name="B", price_cents=200)
            )

    async def test_does_not_persist_when_sku_already_exists(
        self, use_case: CreateProduct, repository: ProductRepository
    ) -> None:
        await use_case.execute(CreateProductCommand(sku="SKU-1", name="A", price_cents=100))

        with pytest.raises(DuplicateSkuError):
            await use_case.execute(
                CreateProductCommand(sku="SKU-1", name="B", price_cents=200)
            )

        stored = await repository.list(limit=10, offset=0)
        assert len(stored) == 1
        assert stored[0].name == "A"

    async def test_propagates_domain_invariant_errors(
        self, use_case: CreateProduct, repository: ProductRepository
    ) -> None:
        command = CreateProductCommand(sku="SKU-1", name="Widget", price_cents=-1)

        with pytest.raises(InvalidProductError, match="price_cents"):
            await use_case.execute(command)

        stored = await repository.list(limit=10, offset=0)
        assert stored == []
