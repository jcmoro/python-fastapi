from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

from contexts.assistant.domain.assessment_usage import AssessmentUsage
from contexts.assistant.domain.exceptions import InvalidAssessmentError

__all__ = [
    "Assessment",
    "AssessmentFailure",
    "AssessmentUsage",
    "Candidate",
    "RubricAnswers",
]


@dataclass(frozen=True, slots=True)
class Candidate:
    product_id: UUID
    sku: str
    name: str
    price_cents: int
    currency: str
    content: str
    retrieval_score: float


@dataclass(frozen=True, slots=True)
class RubricAnswers:
    meets_requirements: float
    suitable_for_use: float

    def __post_init__(self) -> None:
        for name in ("meets_requirements", "suitable_for_use"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise InvalidAssessmentError(f"{name} must be a probability in [0, 1]")


class AssessmentFailure(str, Enum):
    INVALID_SAMPLE = "invalid_sample"
    ERROR = "error"
    DEADLINE = "deadline"


@dataclass(frozen=True, slots=True)
class Assessment:
    product_id: UUID
    answers: RubricAnswers | None
    usage: AssessmentUsage = field(default_factory=AssessmentUsage)
    failure: AssessmentFailure | None = None
