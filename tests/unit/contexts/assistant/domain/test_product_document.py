from uuid import UUID, uuid4

from contexts.assistant.domain.catalog_product import CatalogProduct
from contexts.assistant.domain.product_document import ProductDocument

MODEL = "test-model"


def _product(
    *,
    product_id: UUID | None = None,
    name: str = "Blue widget",
    price_cents: int = 1999,
) -> CatalogProduct:
    return CatalogProduct(
        product_id=product_id or uuid4(),
        sku="WIDGET-001",
        name=name,
        price_cents=price_cents,
        currency="EUR",
    )


class TestFromCatalogProduct:
    def test_renders_sku_name_and_price(self) -> None:
        document = ProductDocument.from_catalog_product(_product(), embedding_model=MODEL)

        assert document.content == "SKU: WIDGET-001\nName: Blue widget\nPrice: 19.99 EUR"

    def test_renders_cents_with_two_digits(self) -> None:
        product = _product(price_cents=5)

        document = ProductDocument.from_catalog_product(product, embedding_model=MODEL)

        assert document.content.endswith("Price: 0.05 EUR")

    def test_keeps_product_id(self) -> None:
        product = _product()

        document = ProductDocument.from_catalog_product(product, embedding_model=MODEL)

        assert document.product_id == product.product_id

    def test_hash_is_stable_for_the_same_product(self) -> None:
        product = _product()

        first = ProductDocument.from_catalog_product(product, embedding_model=MODEL)
        second = ProductDocument.from_catalog_product(product, embedding_model=MODEL)

        assert first.content_hash == second.content_hash
        assert len(first.content_hash) == 64

    def test_hash_changes_when_the_product_changes(self) -> None:
        product = _product()
        renamed = _product(product_id=product.product_id, name="Red widget")

        original = ProductDocument.from_catalog_product(product, embedding_model=MODEL)
        changed = ProductDocument.from_catalog_product(renamed, embedding_model=MODEL)

        assert original.content_hash != changed.content_hash


class TestContentHashCoversTheModel:
    def test_r2_same_content_with_another_model_has_another_hash(self) -> None:
        product = _product()

        first = ProductDocument.from_catalog_product(product, embedding_model="model-a")
        second = ProductDocument.from_catalog_product(product, embedding_model="model-b")

        assert first.content == second.content
        assert first.content_hash != second.content_hash


class TestCatalogFields:
    def test_a7_carries_the_catalog_fields(self) -> None:
        product = _product()

        document = ProductDocument.from_catalog_product(product, embedding_model=MODEL)

        assert (document.sku, document.name, document.price_cents, document.currency) == (
            "WIDGET-001",
            "Blue widget",
            1999,
            "EUR",
        )
