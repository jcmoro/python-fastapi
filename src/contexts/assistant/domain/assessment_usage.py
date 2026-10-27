from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssessmentUsage:
    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
