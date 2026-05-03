from shared.domain.errors import ConflictError, InvalidInputError, NotFoundError


class InvalidProductError(InvalidInputError):
    """A product cannot be constructed because an invariant is violated."""


class ProductNotFoundError(NotFoundError):
    """The requested product does not exist."""


class DuplicateSkuError(ConflictError):
    """A product with the same SKU already exists."""
