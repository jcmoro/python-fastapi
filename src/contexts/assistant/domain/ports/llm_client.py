from abc import ABC, abstractmethod

from contexts.assistant.domain.completion import Completion


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion: ...
