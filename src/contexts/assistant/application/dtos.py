from __future__ import annotations

from dataclasses import dataclass

from contexts.assistant.domain.completion import Completion


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
class AnswerDTO:
    text: str
    usage: UsageDTO

    @classmethod
    def from_completion(cls, completion: Completion) -> AnswerDTO:
        return cls(
            text=completion.text,
            usage=UsageDTO(
                model=completion.model,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                latency_ms=completion.latency_ms,
            ),
        )
