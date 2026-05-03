from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from contexts.catalog.application.use_cases.create_product import CreateProduct
from contexts.catalog.application.use_cases.delete_product import DeleteProduct
from contexts.catalog.application.use_cases.get_product import GetProduct
from contexts.catalog.application.use_cases.list_products import ListProducts
from contexts.catalog.application.use_cases.update_product import UpdateProduct
from contexts.catalog.domain.ports.product_repository import ProductRepository
from contexts.catalog.infrastructure.persistence.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from shared.infrastructure.database import get_session


def get_product_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProductRepository:
    return SqlAlchemyProductRepository(session)


def get_create_product_use_case(
    repository: Annotated[ProductRepository, Depends(get_product_repository)],
) -> CreateProduct:
    return CreateProduct(repository)


def get_get_product_use_case(
    repository: Annotated[ProductRepository, Depends(get_product_repository)],
) -> GetProduct:
    return GetProduct(repository)


def get_list_products_use_case(
    repository: Annotated[ProductRepository, Depends(get_product_repository)],
) -> ListProducts:
    return ListProducts(repository)


def get_update_product_use_case(
    repository: Annotated[ProductRepository, Depends(get_product_repository)],
) -> UpdateProduct:
    return UpdateProduct(repository)


def get_delete_product_use_case(
    repository: Annotated[ProductRepository, Depends(get_product_repository)],
) -> DeleteProduct:
    return DeleteProduct(repository)
