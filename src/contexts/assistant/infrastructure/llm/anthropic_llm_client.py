import time

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic, RateLimitError
from anthropic.types import TextBlock

from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.ports.llm_client import LLMClient

_UNAVAILABLE_MESSAGE = "the language model is unavailable"


class AnthropicLLMClient(LLMClient):
    def __init__(
        self, client: AsyncAnthropic, model: str, timeout_s: float, max_retries: int
    ) -> None:
        self._client = client.with_options(timeout=timeout_s, max_retries=max_retries)
        self._model = model

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        started = time.perf_counter()
        try:
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except (APIConnectionError, RateLimitError) as exc:
            raise LLMUnavailableError(_UNAVAILABLE_MESSAGE) from exc
        except APIStatusError as exc:
            if exc.status_code < 500:
                raise
            raise LLMUnavailableError(_UNAVAILABLE_MESSAGE) from exc
        latency_ms = round((time.perf_counter() - started) * 1000)

        return Completion(
            text="".join(block.text for block in message.content if isinstance(block, TextBlock)),
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=latency_ms,
        )
