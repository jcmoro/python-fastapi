from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    product_id: UUID
    content: str
    score: float
