from uuid import UUID

from contexts.assistant.domain.catalog_product import CatalogProduct
from contexts.assistant.domain.ports.catalog_reader import CatalogReader
from contexts.assistant.domain.ports.document_index import DocumentIndex
from contexts.assistant.domain.ports.document_search import DocumentSearch
from contexts.assistant.domain.product_document import EmbeddedDocument
from contexts.assistant.domain.retrieved_document import RetrievedDocument


class FakeCatalogReader(CatalogReader):
    def __init__(
        self,
        products: list[CatalogProduct] | None = None,
        unlisted: list[CatalogProduct] | None = None,
    ) -> None:
        self.products = list(products or [])
        self.unlisted = list(unlisted or [])

    async def read_all(self) -> list[CatalogProduct]:
        return list(self.products)

    async def missing(self, product_ids: list[UUID]) -> list[UUID]:
        existing = {p.product_id for p in self.products + self.unlisted}
        return [pid for pid in product_ids if pid not in existing]


class FakeDocumentIndex(DocumentIndex):
    def __init__(self) -> None:
        self.documents: dict[UUID, EmbeddedDocument] = {}
        self.upsert_sizes: list[int] = []

    async def content_hashes(self) -> dict[UUID, str]:
        return {pid: item.document.content_hash for pid, item in self.documents.items()}

    async def upsert(self, documents: list[EmbeddedDocument]) -> None:
        self.upsert_sizes.append(len(documents))
        for item in documents:
            self.documents[item.document.product_id] = item

    async def delete(self, product_ids: list[UUID]) -> None:
        for product_id in product_ids:
            self.documents.pop(product_id, None)


class FakeDocumentSearch(DocumentSearch):
    def __init__(self, results: list[RetrievedDocument] | None = None) -> None:
        self._results = list(results or [])
        self.calls: list[tuple[list[float], int]] = []

    async def search(self, embedding: list[float], k: int) -> list[RetrievedDocument]:
        self.calls.append((embedding, k))
        return self._results[:k]
