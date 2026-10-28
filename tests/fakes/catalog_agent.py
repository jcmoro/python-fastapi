from contexts.assistant.domain.agent import AgentResult
from contexts.assistant.domain.exceptions import LLMUnavailableError
from contexts.assistant.domain.ports.catalog_agent import CatalogAgent


class FakeCatalogAgent(CatalogAgent):
    def __init__(self, result: AgentResult | None = None, *, fail: bool = False) -> None:
        self._result = result
        self._fail = fail
        self.questions: list[str] = []

    async def run(self, question: str) -> AgentResult:
        self.questions.append(question)
        if self._fail or self._result is None:
            raise LLMUnavailableError("the language model is unavailable")
        return self._result
