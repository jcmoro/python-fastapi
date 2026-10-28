from abc import ABC, abstractmethod

from contexts.assistant.domain.agent import AgentResult


class CatalogAgent(ABC):
    @abstractmethod
    async def run(self, question: str) -> AgentResult:
        """Makes at most the configured number of tool calls; past that limit it answers in RAG
        mode with what was retrieved (``stop_reason`` = ``max_steps``). ``recommendation`` comes
        only from the candidate selector, never from the model's text. Raises
        ``LLMUnavailableError`` for transient model failures; configuration errors propagate.
        """
