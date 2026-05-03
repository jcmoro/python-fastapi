from uuid import UUID

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.domain.product import Product
from contexts.catalog.infrastructure.persistence.mappers import to_domain, to_model
from contexts.catalog.infrastructure.persistence.models import ProductModel


class SqlAlchemyProductRepository(ProductRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, product: Product) -> None:
        self._session.add(to_model(product))
        await self._session.flush()

    async def get(self, product_id: UUID) -> Product | None:
        model = await self._session.get(ProductModel, product_id)
        return to_domain(model) if model is not None else None

    async def list(self, *, limit: int, offset: int) -> list[Product]:
        stmt = (
            select(ProductModel)
            .order_by(ProductModel.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [to_domain(m) for m in result.scalars().all()]

    async def update(self, product: Product) -> None:
        model = await self._session.get(ProductModel, product.id)
        if model is None:
            return
        model.sku = product.sku
        model.name = product.name
        model.price_cents = product.price_cents
        model.currency = product.currency
        await self._session.flush()

    async def delete(self, product_id: UUID) -> None:
        await self._session.execute(
            delete(ProductModel).where(ProductModel.id == product_id)
        )
        await self._session.flush()

    async def exists_sku(self, sku: str) -> bool:
        stmt = select(exists().where(ProductModel.sku == sku))
        result = await self._session.execute(stmt)
        return bool(result.scalar())
