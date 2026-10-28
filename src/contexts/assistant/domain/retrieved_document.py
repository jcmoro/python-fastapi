from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    product_id: UUID
    content: str
    score: float
    sku: str | None = None
    name: str | None = None
    price_cents: int | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class IndexedProduct:
    product_id: UUID
    sku: str
    name: str
    price_cents: int
    currency: str
    content: str
