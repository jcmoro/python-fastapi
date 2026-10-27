from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.retrieved_document import RetrievedDocument


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
class AnswerDTO:
    text: str
    sources: tuple[SourceDTO, ...]
    fallback_used: bool
    usage: UsageDTO | None

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
    def fallback(cls, text: str, sources: tuple[SourceDTO, ...]) -> AnswerDTO:
        return cls(text=text, sources=sources, fallback_used=True, usage=None)


@dataclass(frozen=True, slots=True)
class IndexReportDTO:
    indexed: int
    unchanged: int
    deleted: int
