import time

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.ports.llm_client import LLMClient
from contexts.assistant.infrastructure.llm.anthropic_errors import transient_errors_as_unavailable


class AnthropicLLMClient(LLMClient):
    def __init__(
        self, client: AsyncAnthropic, model: str, timeout_s: float, max_retries: int
    ) -> None:
        self._client = client.with_options(timeout=timeout_s, max_retries=max_retries)
        self._model = model

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        started = time.perf_counter()
        with transient_errors_as_unavailable():
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        latency_ms = round((time.perf_counter() - started) * 1000)

        return Completion(
            text="".join(block.text for block in message.content if isinstance(block, TextBlock)),
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=latency_ms,
            stop_reason=message.stop_reason,
        )
