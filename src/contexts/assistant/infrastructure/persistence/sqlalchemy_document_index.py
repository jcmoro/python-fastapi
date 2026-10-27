from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from contexts.assistant.domain.ports.document_index import DocumentIndex
from contexts.assistant.domain.product_document import EmbeddedDocument
from contexts.assistant.infrastructure.persistence.models import ProductDocumentModel


class SqlAlchemyDocumentIndex(DocumentIndex):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def content_hashes(self) -> dict[UUID, str | None]:
        model = ProductDocumentModel
        missing_catalog_column = or_(
            model.sku.is_(None),
            model.name.is_(None),
            model.price_cents.is_(None),
            model.currency.is_(None),
        )
        stored_hash = case((missing_catalog_column, None), else_=model.content_hash)
        result = await self._session.execute(select(model.product_id, stored_hash))
        return dict(result.all())

    async def upsert(self, documents: list[EmbeddedDocument]) -> None:
        if not documents:
            return
        now = datetime.now(timezone.utc)
        stmt = insert(ProductDocumentModel).values(
            [
                {
                    "product_id": item.document.product_id,
                    "sku": item.document.sku,
                    "name": item.document.name,
                    "price_cents": item.document.price_cents,
                    "currency": item.document.currency,
                    "content": item.document.content,
                    "content_hash": item.document.content_hash,
                    "embedding": item.embedding,
                    "updated_at": now,
                }
                for item in documents
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ProductDocumentModel.product_id],
            set_={
                "sku": stmt.excluded.sku,
                "name": stmt.excluded.name,
                "price_cents": stmt.excluded.price_cents,
                "currency": stmt.excluded.currency,
                "content": stmt.excluded.content,
                "content_hash": stmt.excluded.content_hash,
                "embedding": stmt.excluded.embedding,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)

    async def delete(self, product_ids: list[UUID]) -> None:
        if not product_ids:
            return
        await self._session.execute(
            delete(ProductDocumentModel).where(ProductDocumentModel.product_id.in_(product_ids))
        )
