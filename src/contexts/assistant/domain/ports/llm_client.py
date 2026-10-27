from abc import ABC, abstractmethod

from contexts.assistant.domain.completion import Completion


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        """Raises ``LLMUnavailableError`` when the model is unreachable, times out, is rate
        limited or fails server-side. Configuration errors (bad credentials, unknown model,
        invalid request) are not translated and propagate unchanged.
        """
