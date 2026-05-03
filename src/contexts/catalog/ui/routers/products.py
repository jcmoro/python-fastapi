from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from contexts.catalog.application.dtos import (
    CreateProductCommand,
    ListProductsQuery,
    UpdateProductCommand,
)
from contexts.catalog.application.use_cases.create_product import CreateProduct
from contexts.catalog.application.use_cases.delete_product import DeleteProduct
from contexts.catalog.application.use_cases.get_product import GetProduct
from contexts.catalog.application.use_cases.list_products import ListProducts
from contexts.catalog.application.use_cases.update_product import UpdateProduct
from contexts.catalog.ui.dependencies import (
    get_create_product_use_case,
    get_delete_product_use_case,
    get_get_product_use_case,
    get_list_products_use_case,
    get_update_product_use_case,
)
from contexts.catalog.ui.schemas import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/products", tags=["catalog"])


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
    description="Creates a new product. Returns 409 if the SKU already exists.",
    responses={
        409: {"description": "A product with the same SKU already exists."},
        422: {"description": "Invalid product fields."},
    },
)
async def create_product_endpoint(
    body: ProductCreate,
    use_case: Annotated[CreateProduct, Depends(get_create_product_use_case)],
) -> ProductResponse:
    command = CreateProductCommand(
        sku=body.sku,
        name=body.name,
        price_cents=body.price_cents,
        currency=body.currency,
    )
    dto = await use_case.execute(command)
    return ProductResponse.from_dto(dto)


@router.get(
    "",
    response_model=list[ProductResponse],
    status_code=status.HTTP_200_OK,
    summary="List products",
    description="Returns a paginated list of products ordered by creation time.",
)
async def list_products_endpoint(
    use_case: Annotated[ListProducts, Depends(get_list_products_use_case)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductResponse]:
    dtos = await use_case.execute(ListProductsQuery(limit=limit, offset=offset))
    return [ProductResponse.from_dto(d) for d in dtos]


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a product by id",
    description="Returns a single product. 404 if it doesn't exist.",
    responses={404: {"description": "Product not found."}},
)
async def get_product_endpoint(
    product_id: UUID,
    use_case: Annotated[GetProduct, Depends(get_get_product_use_case)],
) -> ProductResponse:
    dto = await use_case.execute(product_id)
    return ProductResponse.from_dto(dto)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a product",
    description="Partially updates a product. SKU is immutable.",
    responses={
        404: {"description": "Product not found."},
        422: {"description": "Invalid product fields."},
    },
)
async def update_product_endpoint(
    product_id: UUID,
    body: ProductUpdate,
    use_case: Annotated[UpdateProduct, Depends(get_update_product_use_case)],
) -> ProductResponse:
    command = UpdateProductCommand(
        product_id=product_id,
        name=body.name,
        price_cents=body.price_cents,
        currency=body.currency,
    )
    dto = await use_case.execute(command)
    return ProductResponse.from_dto(dto)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product",
    description="Removes a product. 404 if it doesn't exist.",
    responses={404: {"description": "Product not found."}},
)
async def delete_product_endpoint(
    product_id: UUID,
    use_case: Annotated[DeleteProduct, Depends(get_delete_product_use_case)],
) -> None:
    await use_case.execute(product_id)
