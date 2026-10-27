from sqlalchemy import Float, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contexts.assistant.domain.ports.document_search import DocumentSearch
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.infrastructure.persistence.models import ProductDocumentModel


class SqlAlchemyDocumentSearch(DocumentSearch):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(self, embedding: list[float], k: int) -> list[RetrievedDocument]:
        distance = ProductDocumentModel.embedding.op("<=>", return_type=Float)(embedding)
        stmt = (
            select(ProductDocumentModel.product_id, ProductDocumentModel.content, distance)
            .order_by(distance)
            .limit(k)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            RetrievedDocument(product_id=product_id, content=content, score=1.0 - float(dist))
            for product_id, content, dist in rows
        ]
