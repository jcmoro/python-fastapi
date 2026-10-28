from abc import ABC, abstractmethod

from contexts.assistant.domain.agent import AgentResult


class CatalogAgent(ABC):
    @abstractmethod
    async def run(self, question: str) -> AgentResult:
        """Makes at most the configured number of tool calls; past that limit it answers in RAG
        mode with what was retrieved (``stop_reason`` = ``max_steps``). ``recommendation`` comes
        only from the candidate selector, never from the model's text. A turn cut off by
        ``max_tokens`` or refused ends the run with ``stop_reason`` = ``model_incomplete`` and the
        model's own reason in ``model_stop_reason``. Raises ``AgentUnavailableError`` for transient
        model failures, carrying the sources, recommendation and usage gathered until then;
        configuration errors propagate.
        """
