from shared.domain.errors import InvalidInputError, ServiceUnavailableError


class InvalidQuestionError(InvalidInputError):
    """A question cannot be constructed because an invariant is violated."""


class LLMUnavailableError(ServiceUnavailableError):
    """The language model could not produce a completion."""
