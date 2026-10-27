import asyncio
from uuid import UUID

from contexts.assistant.domain.candidate import (
    Assessment,
    AssessmentFailure,
    AssessmentUsage,
    Candidate,
    RubricAnswers,
)
from contexts.assistant.domain.ports.candidate_assessor import CandidateAssessor

Outcome = RubricAnswers | Exception | None


class FakeCandidateAssessor(CandidateAssessor):
    def __init__(
        self,
        outcomes: dict[UUID, Outcome] | None = None,
        delays: dict[UUID, float] | None = None,
        default: Outcome = None,
    ) -> None:
        self._outcomes = outcomes or {}
        self._delays = delays or {}
        self._default = default
        self.assessed: list[UUID] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.cancelled = 0

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-assessor"

    async def assess(self, question: str, candidate: Candidate) -> Assessment:
        self.assessed.append(candidate.product_id)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self._delays.get(candidate.product_id, 0.01))
        except asyncio.CancelledError:
            self.cancelled += 1
            self.in_flight -= 1
            raise
        try:
            outcome = self._outcomes.get(candidate.product_id, self._default)
            if isinstance(outcome, Exception):
                raise outcome
            usage = AssessmentUsage(api_calls=3, input_tokens=100, output_tokens=10)
            failure = AssessmentFailure.INVALID_SAMPLE if outcome is None else None
            return Assessment(
                product_id=candidate.product_id, answers=outcome, usage=usage, failure=failure
            )
        finally:
            self.in_flight -= 1
