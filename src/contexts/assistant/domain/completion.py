from dataclasses import dataclass

INCOMPLETE_STOP_REASONS = frozenset({"max_tokens", "refusal"})


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    stop_reason: str | None = None
