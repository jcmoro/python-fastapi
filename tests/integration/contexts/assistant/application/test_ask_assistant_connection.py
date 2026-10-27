from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.fakes.embedding_client import FakeEmbeddingClient
from tests.fakes.llm_client import FakeLLMClient

from contexts.assistant.application.dtos import AskCommand
from contexts.assistant.application.use_cases.ask_assistant import AskAssistant
from contexts.assistant.domain.completion import Completion
from contexts.assistant.infrastructure.persistence.models import EMBEDDING_DIMENSIONS
from contexts.assistant.infrastructure.persistence.sqlalchemy_document_search import (
    SqlAlchemyDocumentSearch,
)

QUESTION = "What is a widget?"


class PoolProbingLLMClient(FakeLLMClient):
    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__()
        self._engine = engine
        self.checked_out_during_call: list[int] = []

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        self.checked_out_during_call.append(self._engine.pool.checkedout())
        return await super().complete(system=system, prompt=prompt, max_tokens=max_tokens)


async def test_r5_no_connection_is_held_while_the_llm_answers(db_engine: AsyncEngine) -> None:
    llm_client = PoolProbingLLMClient(db_engine)
    embeddings = FakeEmbeddingClient({QUESTION: [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)})
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    use_case = AskAssistant(
        llm_client,
        embeddings,
        SqlAlchemyDocumentSearch(session_factory),
        max_tokens=16,
        top_k=5,
    )

    await use_case.execute(AskCommand(question=QUESTION))

    assert llm_client.checked_out_during_call == [0]
