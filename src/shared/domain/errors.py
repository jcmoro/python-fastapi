class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class InvalidInputError(DomainError):
    pass


class ServiceUnavailableError(DomainError):
    pass
