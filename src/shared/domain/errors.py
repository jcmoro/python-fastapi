class DomainError(Exception):
    """Base class for all domain errors that map to HTTP responses."""


class NotFoundError(DomainError):
    """Resource not found. Maps to HTTP 404."""


class ConflictError(DomainError):
    """Domain-level conflict, e.g. uniqueness violation. Maps to HTTP 409."""


class InvalidInputError(DomainError):
    """A domain invariant has been violated. Maps to HTTP 422."""
