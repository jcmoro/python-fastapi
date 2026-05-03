from contexts.catalog.domain.product import Product
from contexts.catalog.infrastructure.persistence.models import ProductModel


def to_domain(model: ProductModel) -> Product:
    return Product(
        id=model.id,
        sku=model.sku,
        name=model.name,
        price_cents=model.price_cents,
        currency=model.currency,
        created_at=model.created_at,
    )


def to_model(product: Product) -> ProductModel:
    return ProductModel(
        id=product.id,
        sku=product.sku,
        name=product.name,
        price_cents=product.price_cents,
        currency=product.currency,
        created_at=product.created_at,
    )
