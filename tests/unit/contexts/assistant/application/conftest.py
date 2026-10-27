from dataclasses import dataclass

import pytest

from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.ports.llm_client import LLMClient


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    system: str
    prompt: str
    max_tokens: int


class FakeLLMClient(LLMClient):
    """Scripted LLMClient for unit tests. Mocks at the port boundary."""

    def __init__(self, completion: Completion | None = None, *, fail: bool = False) -> None:
        self._completion = completion or Completion(
            text="An answer.",
            model="fake-model",
            input_tokens=12,
            output_tokens=3,
            latency_ms=42,
        )
        self._fail = fail
        self.requests: list[CompletionRequest] = []

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        self.requests.append(CompletionRequest(system=system, prompt=prompt, max_tokens=max_tokens))
        if self._fail:
            raise LLMUnavailableError("the language model is unavailable")
        return self._completion


@pytest.fixture
def llm_client() -> FakeLLMClient:
    return FakeLLMClient()
