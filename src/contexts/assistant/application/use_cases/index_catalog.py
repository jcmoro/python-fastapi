from contexts.assistant.application.dtos import IndexReportDTO
from contexts.assistant.domain.ports.catalog_reader import CatalogReader
from contexts.assistant.domain.ports.document_index import DocumentIndex
from contexts.assistant.domain.ports.embedding_client import EmbeddingClient
from contexts.assistant.domain.product_document import EmbeddedDocument, ProductDocument

DEFAULT_BATCH_SIZE = 256


class IndexCatalog:
    def __init__(
        self,
        catalog_reader: CatalogReader,
        embedding_client: EmbeddingClient,
        document_index: DocumentIndex,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._catalog_reader = catalog_reader
        self._embedding_client = embedding_client
        self._document_index = document_index
        self._batch_size = batch_size

    async def execute(self) -> IndexReportDTO:
        products = await self._catalog_reader.read_all()
        model = self._embedding_client.model_name
        documents = [
            ProductDocument.from_catalog_product(product, embedding_model=model)
            for product in products
        ]
        stored_hashes = await self._document_index.content_hashes()

        changed = [
            doc for doc in documents if stored_hashes.get(doc.product_id) != doc.content_hash
        ]
        for start in range(0, len(changed), self._batch_size):
            await self._index_batch(changed[start : start + self._batch_size])

        unlisted_ids = sorted(set(stored_hashes) - {doc.product_id for doc in documents})
        orphan_ids = await self._catalog_reader.missing(unlisted_ids) if unlisted_ids else []
        if orphan_ids:
            await self._document_index.delete(orphan_ids)

        return IndexReportDTO(
            indexed=len(changed),
            unchanged=len(documents) - len(changed),
            deleted=len(orphan_ids),
        )

    async def _index_batch(self, batch: list[ProductDocument]) -> None:
        embeddings = await self._embedding_client.embed([doc.content for doc in batch])
        await self._document_index.upsert(
            [
                EmbeddedDocument(document=doc, embedding=embedding)
                for doc, embedding in zip(batch, embeddings, strict=True)
            ]
        )
