from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CatalogProduct:
    product_id: UUID
    sku: str
    name: str
    price_cents: int
    currency: str
