from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from contexts.catalog.domain.exceptions import InvalidProductError
from contexts.catalog.domain.product import Product


class TestCreate:
    def test_generates_uuid_when_not_provided(self) -> None:
        product = Product.create(sku="SKU-1", name="Widget", price_cents=999)

        assert isinstance(product.id, UUID)

    def test_uses_provided_id(self) -> None:
        product_id = uuid4()
        product = Product.create(
            sku="SKU-1", name="Widget", price_cents=999, product_id=product_id
        )

        assert product.id == product_id

    def test_generates_utc_timestamp_when_not_provided(self) -> None:
        product = Product.create(sku="SKU-1", name="Widget", price_cents=999)

        assert product.created_at.tzinfo is not None
        assert product.created_at.utcoffset() == datetime.now(timezone.utc).utcoffset()

    def test_defaults_currency_to_eur(self) -> None:
        product = Product.create(sku="SKU-1", name="Widget", price_cents=999)

        assert product.currency == "EUR"

    def test_normalises_currency_to_uppercase(self) -> None:
        product = Product.create(sku="SKU-1", name="Widget", price_cents=999, currency="usd")

        assert product.currency == "USD"

    def test_strips_whitespace_from_sku_and_name(self) -> None:
        product = Product.create(sku="  SKU-1  ", name="  Widget  ", price_cents=999)

        assert product.sku == "SKU-1"
        assert product.name == "Widget"


class TestInvariants:
    @pytest.mark.parametrize("sku", ["", "   "])
    def test_rejects_empty_sku(self, sku: str) -> None:
        with pytest.raises(InvalidProductError, match="sku"):
            Product.create(sku=sku, name="Widget", price_cents=999)

    def test_rejects_sku_too_long(self) -> None:
        with pytest.raises(InvalidProductError, match="sku"):
            Product.create(sku="X" * 65, name="Widget", price_cents=999)

    @pytest.mark.parametrize("name", ["", "   "])
    def test_rejects_empty_name(self, name: str) -> None:
        with pytest.raises(InvalidProductError, match="name"):
            Product.create(sku="SKU-1", name=name, price_cents=999)

    def test_rejects_name_too_long(self) -> None:
        with pytest.raises(InvalidProductError, match="name"):
            Product.create(sku="SKU-1", name="X" * 201, price_cents=999)

    def test_rejects_negative_price(self) -> None:
        with pytest.raises(InvalidProductError, match="price_cents"):
            Product.create(sku="SKU-1", name="Widget", price_cents=-1)

    def test_accepts_zero_price(self) -> None:
        product = Product.create(sku="SKU-1", name="Widget", price_cents=0)

        assert product.price_cents == 0

    @pytest.mark.parametrize("currency", ["EU", "EURO", "EU1", "12A"])
    def test_rejects_invalid_currency(self, currency: str) -> None:
        with pytest.raises(InvalidProductError, match="currency"):
            Product.create(sku="SKU-1", name="Widget", price_cents=999, currency=currency)


class TestWithChanges:
    def test_returns_new_instance(self) -> None:
        original = Product.create(sku="SKU-1", name="Widget", price_cents=999)
        updated = original.with_changes(name="Gadget")

        assert updated is not original
        assert original.name == "Widget"

    def test_preserves_untouched_fields(self) -> None:
        original = Product.create(sku="SKU-1", name="Widget", price_cents=999, currency="USD")
        updated = original.with_changes(name="Gadget")

        assert updated.id == original.id
        assert updated.sku == original.sku
        assert updated.price_cents == original.price_cents
        assert updated.currency == original.currency
        assert updated.created_at == original.created_at

    def test_updates_provided_fields(self) -> None:
        original = Product.create(sku="SKU-1", name="Widget", price_cents=999)
        updated = original.with_changes(name="Gadget", price_cents=1500, currency="usd")

        assert updated.name == "Gadget"
        assert updated.price_cents == 1500
        assert updated.currency == "USD"

    def test_validates_invariants_on_update(self) -> None:
        product = Product.create(sku="SKU-1", name="Widget", price_cents=999)

        with pytest.raises(InvalidProductError, match="price_cents"):
            product.with_changes(price_cents=-1)
