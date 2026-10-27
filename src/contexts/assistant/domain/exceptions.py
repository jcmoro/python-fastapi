from contexts.assistant.domain.assessment_usage import AssessmentUsage
from shared.domain.errors import DomainError, InvalidInputError, ServiceUnavailableError


class InvalidQuestionError(InvalidInputError):
    pass


class LLMUnavailableError(ServiceUnavailableError):
    pass


class InvalidAssessmentError(DomainError):
    pass


class AssessmentUnavailableError(LLMUnavailableError):
    def __init__(self, usage: AssessmentUsage) -> None:
        super().__init__("the language model is unavailable")
        self.usage = usage
