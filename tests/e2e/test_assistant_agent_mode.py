from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from main import create_app
from tests.fakes.catalog_agent import FakeCatalogAgent
from tests.fakes.documents import FakeDocumentSearch
from tests.fakes.embedding_client import FakeEmbeddingClient
from tests.fakes.llm_client import FakeLLMClient

from contexts.assistant.domain.agent import (
    AgentRecommendation,
    AgentResult,
    AgentStopReason,
    AgentUsage,
)
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.domain.selection import SelectionReason
from contexts.assistant.ui.dependencies import (
    get_document_search,
    get_embedding_client,
    get_llm_client,
    get_mode_catalog_agent,
)

BOOT = RetrievedDocument(
    product_id=uuid4(), content="SKU: BOOT-1\nName: Winter boot", score=0.9, sku="BOOT-1"
)
USAGE = AgentUsage(
    model="claude-test", tool_calls=1, input_tokens=50, output_tokens=9, latency_ms=10
)

ClientFactory = Callable[[FakeCatalogAgent], AsyncClient]


def _result(recommendation: AgentRecommendation | None) -> AgentResult:
    return AgentResult(
        text="Answer.",
        sources=(BOOT,),
        recommendation=recommendation,
        stop_reason=AgentStopReason.ANSWERED,
        usage=USAGE,
    )


@pytest_asyncio.fixture
async def agent_client() -> AsyncIterator[ClientFactory]:
    clients: list[AsyncClient] = []

    def _factory(agent: FakeCatalogAgent) -> AsyncClient:
        application = create_app()
        llm, embeddings, search = FakeLLMClient(), FakeEmbeddingClient(), FakeDocumentSearch()
        application.dependency_overrides[get_mode_catalog_agent] = lambda: agent
        application.dependency_overrides[get_llm_client] = lambda: llm
        application.dependency_overrides[get_embedding_client] = lambda: embeddings
        application.dependency_overrides[get_document_search] = lambda: search
        client = AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver")
        clients.append(client)
        return client

    yield _factory
    for client in clients:
        await client.aclose()


QUESTION = {"question": "Which boot for winter hiking?"}


class TestAgentMode:
    async def test_b10_a_chosen_product_comes_back_as_an_object(
        self, agent_client: ClientFactory
    ) -> None:
        agent = FakeCatalogAgent(
            _result(
                AgentRecommendation(
                    product_id=BOOT.product_id,
                    sku="BOOT-1",
                    score=1.0,
                    reason=SelectionReason.CHOSEN,
                )
            )
        )

        response = await agent_client(agent).post("/assistant/ask", json=QUESTION)

        assert response.status_code == 200
        assert response.json()["recommendation"] == {
            "product_id": str(BOOT.product_id),
            "sku": "BOOT-1",
            "score": 1.0,
            "reason": "chosen",
        }

    async def test_b10_selector_ran_without_choosing(self, agent_client: ClientFactory) -> None:
        agent = FakeCatalogAgent(
            _result(
                AgentRecommendation(
                    product_id=None, sku=None, score=None, reason=SelectionReason.BELOW_THRESHOLD
                )
            )
        )

        response = await agent_client(agent).post("/assistant/ask", json=QUESTION)

        assert response.json()["recommendation"] == {
            "product_id": None,
            "sku": None,
            "score": None,
            "reason": "below_threshold",
        }

    async def test_b10_agent_answered_without_recommending(
        self, agent_client: ClientFactory
    ) -> None:
        response = await agent_client(FakeCatalogAgent(_result(None))).post(
            "/assistant/ask", json=QUESTION
        )

        assert response.json()["recommendation"] is None

    async def test_b15_stop_reason_is_not_part_of_the_http_response(
        self, agent_client: ClientFactory
    ) -> None:
        response = await agent_client(FakeCatalogAgent(_result(None))).post(
            "/assistant/ask", json=QUESTION
        )

        assert "stop_reason" not in response.json()
        assert set(response.json()) == {
            "text",
            "sources",
            "fallback_used",
            "usage",
            "recommendation",
        }
