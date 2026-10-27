import time

from anthropic import APIError, AsyncAnthropic
from anthropic.types import TextBlock

from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.ports.llm_client import LLMClient


class AnthropicLLMClient(LLMClient):
    def __init__(self, client: AsyncAnthropic, model: str, timeout_s: float) -> None:
        self._client = client
        self._model = model
        self._timeout_s = timeout_s

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        started = time.perf_counter()
        try:
            message = await self._client.with_options(timeout=self._timeout_s).messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except APIError as exc:
            raise LLMUnavailableError("the language model is unavailable") from exc
        latency_ms = round((time.perf_counter() - started) * 1000)

        return Completion(
            text="".join(block.text for block in message.content if isinstance(block, TextBlock)),
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=latency_ms,
        )
