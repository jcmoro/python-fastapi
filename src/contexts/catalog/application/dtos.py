from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from contexts.catalog.domain.product import Product


@dataclass(frozen=True, slots=True)
class ProductDTO:
    id: UUID
    sku: str
    name: str
    price_cents: int
    currency: str
    created_at: datetime

    @classmethod
    def from_entity(cls, product: Product) -> ProductDTO:
        return cls(
            id=product.id,
            sku=product.sku,
            name=product.name,
            price_cents=product.price_cents,
            currency=product.currency,
            created_at=product.created_at,
        )


@dataclass(frozen=True, slots=True)
class CreateProductCommand:
    sku: str
    name: str
    price_cents: int
    currency: str = "EUR"


@dataclass(frozen=True, slots=True)
class ListProductsQuery:
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class UpdateProductCommand:
    product_id: UUID
    name: str | None = None
    price_cents: int | None = None
    currency: str | None = None
