from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.domain.selection import SelectionReason


class AgentStopReason(str, Enum):
    ANSWERED = "answered"
    MAX_STEPS = "max_steps"
    MODEL_INCOMPLETE = "model_incomplete"


@dataclass(frozen=True, slots=True)
class AgentRecommendation:
    product_id: UUID | None
    sku: str | None
    score: float | None
    reason: SelectionReason


@dataclass(frozen=True, slots=True)
class AgentUsage:
    model: str
    tool_calls: int
    input_tokens: int
    output_tokens: int
    latency_ms: int


@dataclass(frozen=True, slots=True)
class AgentResult:
    text: str
    sources: tuple[RetrievedDocument, ...]
    recommendation: AgentRecommendation | None
    stop_reason: AgentStopReason
    usage: AgentUsage
    model_stop_reason: str | None = None


class AgentUnavailableError(LLMUnavailableError):
    def __init__(
        self,
        *,
        sources: tuple[RetrievedDocument, ...],
        recommendation: AgentRecommendation | None,
        usage: AgentUsage,
    ) -> None:
        super().__init__("the language model is unavailable")
        self.sources = sources
        self.recommendation = recommendation
        self.usage = usage
