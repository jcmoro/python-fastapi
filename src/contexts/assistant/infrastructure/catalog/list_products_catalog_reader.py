from uuid import UUID

from contexts.assistant.domain.catalog_product import CatalogProduct
from contexts.assistant.domain.ports.catalog_reader import CatalogReader
from contexts.catalog.application.dtos import ListProductsQuery, ProductDTO
from contexts.catalog.application.use_cases.get_product import GetProduct
from contexts.catalog.application.use_cases.list_products import ListProducts
from shared.domain.errors import NotFoundError

DEFAULT_PAGE_SIZE = 200


class ListProductsCatalogReader(CatalogReader):
    def __init__(
        self,
        list_products: ListProducts,
        get_product: GetProduct,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self._list_products = list_products
        self._get_product = get_product
        self._page_size = page_size

    async def read_all(self) -> list[CatalogProduct]:
        products: dict[UUID, CatalogProduct] = {}
        offset = 0
        while True:
            page = await self._list_products.execute(
                ListProductsQuery(limit=self._page_size, offset=offset)
            )
            for dto in page:
                products[dto.id] = _to_catalog_product(dto)
            if len(page) < self._page_size:
                return list(products.values())
            offset += self._page_size

    async def missing(self, product_ids: list[UUID]) -> list[UUID]:
        return [product_id for product_id in product_ids if not await self._exists(product_id)]

    async def _exists(self, product_id: UUID) -> bool:
        try:
            await self._get_product.execute(product_id)
        except NotFoundError:
            return False
        return True


def _to_catalog_product(dto: ProductDTO) -> CatalogProduct:
    return CatalogProduct(
        product_id=dto.id,
        sku=dto.sku,
        name=dto.name,
        price_cents=dto.price_cents,
        currency=dto.currency,
    )
