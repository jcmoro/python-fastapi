from sqlalchemy import Float, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contexts.assistant.domain.ports.document_search import DocumentSearch
from contexts.assistant.domain.retrieved_document import IndexedProduct, RetrievedDocument
from contexts.assistant.infrastructure.persistence.models import ProductDocumentModel


class SqlAlchemyDocumentSearch(DocumentSearch):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(self, embedding: list[float], k: int) -> list[RetrievedDocument]:
        model = ProductDocumentModel
        distance = model.embedding.op("<=>", return_type=Float)(embedding)
        stmt = (
            select(
                model.product_id,
                model.content,
                distance,
                model.sku,
                model.name,
                model.price_cents,
                model.currency,
            )
            .order_by(distance)
            .limit(k)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            RetrievedDocument(
                product_id=product_id,
                content=content,
                score=1.0 - float(dist),
                sku=sku,
                name=name,
                price_cents=price_cents,
                currency=currency,
            )
            for product_id, content, dist, sku, name, price_cents, currency in rows
        ]

    async def find_by_sku(self, sku: str) -> IndexedProduct | None:
        model = ProductDocumentModel
        stmt = select(
            model.product_id,
            model.sku,
            model.name,
            model.price_cents,
            model.currency,
            model.content,
        ).where(model.sku == sku)
        async with self._session_factory() as session:
            row = (await session.execute(stmt)).one_or_none()
        if row is None:
            return None
        product_id, found_sku, name, price_cents, currency, content = row
        if found_sku is None or name is None or price_cents is None or currency is None:
            return None
        return IndexedProduct(
            product_id=product_id,
            sku=found_sku,
            name=name,
            price_cents=price_cents,
            currency=currency,
            content=content,
        )
