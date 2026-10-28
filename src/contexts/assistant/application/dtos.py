from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from contexts.assistant.domain.agent import AgentRecommendation, AgentStopReason
from contexts.assistant.domain.candidate import Candidate
from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.domain.selection import SelectionReason


@dataclass(frozen=True, slots=True)
class AskCommand:
    question: str


@dataclass(frozen=True, slots=True)
class UsageDTO:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


@dataclass(frozen=True, slots=True)
class SourceDTO:
    product_id: UUID
    content: str
    score: float

    @classmethod
    def from_retrieved(cls, document: RetrievedDocument) -> SourceDTO:
        return cls(product_id=document.product_id, content=document.content, score=document.score)


@dataclass(frozen=True, slots=True)
class RecommendationSummaryDTO:
    product_id: UUID | None
    sku: str | None
    score: float | None
    reason: SelectionReason

    @classmethod
    def from_agent(cls, recommendation: AgentRecommendation) -> RecommendationSummaryDTO:
        return cls(
            product_id=recommendation.product_id,
            sku=recommendation.sku,
            score=recommendation.score,
            reason=recommendation.reason,
        )


@dataclass(frozen=True, slots=True)
class AnswerDTO:
    text: str
    sources: tuple[SourceDTO, ...]
    fallback_used: bool
    usage: UsageDTO | None
    recommendation: RecommendationSummaryDTO | None = None
    stop_reason: AgentStopReason | None = None
    model_stop_reason: str | None = None

    @classmethod
    def from_completion(cls, completion: Completion, sources: tuple[SourceDTO, ...]) -> AnswerDTO:
        return cls(
            text=completion.text,
            sources=sources,
            fallback_used=False,
            usage=UsageDTO(
                model=completion.model,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                latency_ms=completion.latency_ms,
            ),
        )

    @classmethod
    def fallback(
        cls,
        text: str,
        sources: tuple[SourceDTO, ...],
        *,
        recommendation: RecommendationSummaryDTO | None = None,
        stop_reason: AgentStopReason | None = None,
        model_stop_reason: str | None = None,
    ) -> AnswerDTO:
        return cls(
            text=text,
            sources=sources,
            fallback_used=True,
            usage=None,
            recommendation=recommendation,
            stop_reason=stop_reason,
            model_stop_reason=model_stop_reason,
        )


@dataclass(frozen=True, slots=True)
class IndexReportDTO:
    indexed: int
    unchanged: int
    deleted: int


@dataclass(frozen=True, slots=True)
class CandidateDTO:
    product_id: UUID
    sku: str
    name: str
    price_cents: int
    currency: str
    retrieval_score: float

    @classmethod
    def from_candidate(cls, candidate: Candidate) -> CandidateDTO:
        return cls(
            product_id=candidate.product_id,
            sku=candidate.sku,
            name=candidate.name,
            price_cents=candidate.price_cents,
            currency=candidate.currency,
            retrieval_score=candidate.retrieval_score,
        )


@dataclass(frozen=True, slots=True)
class RecommendationDTO:
    product_id: UUID | None
    sku: str | None
    score: float | None
    reason: SelectionReason
    fallback_used: bool
    candidates: tuple[CandidateDTO, ...]
    assessed: int
