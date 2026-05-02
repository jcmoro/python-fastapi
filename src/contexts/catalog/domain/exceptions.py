class CatalogError(Exception):
    """Base class for catalog domain errors."""


class InvalidProductError(CatalogError):
    """A product cannot be constructed because an invariant is violated."""


class ProductNotFoundError(CatalogError):
    """The requested product does not exist."""


class DuplicateSkuError(CatalogError):
    """A product with the same SKU already exists."""
