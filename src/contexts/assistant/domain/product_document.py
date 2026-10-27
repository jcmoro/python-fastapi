from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from contexts.assistant.domain.catalog_product import CatalogProduct


@dataclass(frozen=True, slots=True)
class ProductDocument:
    product_id: UUID
    content: str
    content_hash: str

    @classmethod
    def from_catalog_product(
        cls, product: CatalogProduct, *, embedding_model: str
    ) -> ProductDocument:
        content = _render(product)
        fingerprint = f"{embedding_model}\n{content}"
        return cls(
            product_id=product.product_id,
            content=content,
            content_hash=hashlib.sha256(fingerprint.encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class EmbeddedDocument:
    document: ProductDocument
    embedding: list[float]


def _render(product: CatalogProduct) -> str:
    units, cents = divmod(product.price_cents, 100)
    return (
        f"SKU: {product.sku}\n"
        f"Name: {product.name}\n"
        f"Price: {units}.{cents:02d} {product.currency}"
    )
