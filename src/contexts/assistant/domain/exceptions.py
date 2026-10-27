from shared.domain.errors import InvalidInputError, ServiceUnavailableError


class InvalidQuestionError(InvalidInputError):
    pass


class LLMUnavailableError(ServiceUnavailableError):
    pass
