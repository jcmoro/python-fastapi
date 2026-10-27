import asyncio
import json
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from anthropic.types import Message, OutputConfigParam, TextBlock

from contexts.assistant.domain.candidate import (
    Assessment,
    AssessmentFailure,
    AssessmentUsage,
    Candidate,
    RubricAnswers,
)
from contexts.assistant.domain.exceptions import AssessmentUnavailableError, LLMUnavailableError
from contexts.assistant.domain.ports.candidate_assessor import CandidateAssessor
from contexts.assistant.domain.rubric import RUBRIC
from contexts.assistant.infrastructure.llm.anthropic_errors import transient_errors_as_unavailable

PROVIDER = "claude"

SYSTEM_PROMPT = (
    "You assess one catalog product against a question. Answer each rubric question with "
    "true (yes) or false (no), using only the product data given.\n\n"
    + "\n".join(
        f"- {question.id}: {question.instructions} "
        f"Yes means: {question.yes_means} No means: {question.no_means}"
        for question in RUBRIC
    )
)

OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {question.id: {"type": "boolean"} for question in RUBRIC},
    "required": [question.id for question in RUBRIC],
    "additionalProperties": False,
}

OUTPUT_CONFIG: OutputConfigParam = {
    "effort": "low",
    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
}


@dataclass(frozen=True, slots=True)
class _Verdict:
    meets_requirements: bool
    suitable_for_use: bool


class ClaudeCandidateAssessor(CandidateAssessor):
    def __init__(
        self,
        *,
        client: AsyncAnthropic,
        model: str,
        timeout_s: float,
        max_retries: int,
        samples: int,
        max_tokens: int,
        max_concurrency: int,
    ) -> None:
        self._client = client.with_options(timeout=timeout_s, max_retries=max_retries)
        self._model = model
        self._samples = samples
        self._max_tokens = max_tokens
        self._calls = asyncio.Semaphore(max_concurrency)

    @property
    def provider(self) -> str:
        return PROVIDER

    @property
    def model_name(self) -> str:
        return self._model

    async def assess(self, question: str, candidate: Candidate) -> Assessment:
        outcomes = await asyncio.gather(
            *(self._ask(question, candidate) for _ in range(self._samples)),
            return_exceptions=True,
        )
        messages = [outcome for outcome in outcomes if isinstance(outcome, Message)]
        usage = AssessmentUsage(
            api_calls=self._samples,
            input_tokens=sum(message.usage.input_tokens for message in messages),
            output_tokens=sum(message.usage.output_tokens for message in messages),
        )

        errors = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        fatal = [error for error in errors if not isinstance(error, LLMUnavailableError)]
        if fatal:
            raise fatal[0]
        if errors:
            raise AssessmentUnavailableError(usage) from errors[0]

        verdicts = [_parse(message) for message in messages]
        if any(verdict is None for verdict in verdicts):
            return Assessment(
                product_id=candidate.product_id,
                answers=None,
                usage=usage,
                failure=AssessmentFailure.INVALID_SAMPLE,
            )
        valid = [verdict for verdict in verdicts if verdict is not None]
        answers = RubricAnswers(
            meets_requirements=sum(v.meets_requirements for v in valid) / self._samples,
            suitable_for_use=sum(v.suitable_for_use for v in valid) / self._samples,
        )
        return Assessment(product_id=candidate.product_id, answers=answers, usage=usage)

    async def _ask(self, question: str, candidate: Candidate) -> Message:
        state = json.dumps({"question": question, "product": candidate.content})
        async with self._calls:
            with transient_errors_as_unavailable():
                return await self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": state}],
                    output_config=OUTPUT_CONFIG,
                )


def _parse(message: Message) -> _Verdict | None:
    if message.stop_reason != "end_turn":
        return None
    text = "".join(block.text for block in message.content if isinstance(block, TextBlock))
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or set(data) != {question.id for question in RUBRIC}:
        return None
    meets, suitable = data["meets_requirements"], data["suitable_for_use"]
    if not isinstance(meets, bool) or not isinstance(suitable, bool):
        return None
    return _Verdict(meets_requirements=meets, suitable_for_use=suitable)
