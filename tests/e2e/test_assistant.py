from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from main import create_app
from tests.fakes.documents import FakeDocumentSearch
from tests.fakes.embedding_client import FakeEmbeddingClient
from tests.fakes.llm_client import FakeLLMClient

from contexts.assistant.application.use_cases.ask_assistant import FALLBACK_WITH_SOURCES
from contexts.assistant.domain.completion import Completion
from contexts.assistant.domain.retrieved_document import RetrievedDocument
from contexts.assistant.ui.dependencies import (
    get_document_search,
    get_embedding_client,
    get_llm_client,
)

WIDGET = RetrievedDocument(
    product_id=uuid4(), content="SKU: W-1\nName: Blue widget\nPrice: 19.99 EUR", score=0.9
)

ClientFactory = Callable[..., AsyncClient]


@pytest_asyncio.fixture
async def client_with() -> AsyncIterator[ClientFactory]:
    clients: list[AsyncClient] = []

    def _factory(
        llm_client: FakeLLMClient, search: FakeDocumentSearch | None = None
    ) -> AsyncClient:
        application = create_app()
        document_search = search or FakeDocumentSearch([WIDGET])
        embedding_client = FakeEmbeddingClient()
        application.dependency_overrides[get_llm_client] = lambda: llm_client
        application.dependency_overrides[get_embedding_client] = lambda: embedding_client
        application.dependency_overrides[get_document_search] = lambda: document_search
        client = AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver")
        clients.append(client)
        return client

    yield _factory
    for client in clients:
        await client.aclose()


def _source_json(document: RetrievedDocument) -> dict[str, object]:
    return {
        "product_id": str(document.product_id),
        "content": document.content,
        "score": document.score,
    }


class TestAsk:
    async def test_c7_returns_200_with_answer_sources_and_usage(
        self, client_with: ClientFactory
    ) -> None:
        completion = Completion(
            text="The blue widget costs 19.99 EUR.",
            model="claude-test",
            input_tokens=50,
            output_tokens=9,
            latency_ms=120,
        )
        client = client_with(FakeLLMClient(completion))

        response = await client.post("/assistant/ask", json={"question": "How much is a widget?"})

        assert response.status_code == 200
        assert response.json() == {
            "text": "The blue widget costs 19.99 EUR.",
            "sources": [_source_json(WIDGET)],
            "fallback_used": False,
            "recommendation": None,
            "usage": {
                "model": "claude-test",
                "input_tokens": 50,
                "output_tokens": 9,
                "latency_ms": 120,
            },
        }

    async def test_returns_empty_sources_when_index_is_empty(
        self, client_with: ClientFactory
    ) -> None:
        client = client_with(FakeLLMClient(), FakeDocumentSearch())

        response = await client.post("/assistant/ask", json={"question": "What is a widget?"})

        assert response.status_code == 200
        assert response.json()["sources"] == []

    async def test_returns_422_on_empty_question(self, client_with: ClientFactory) -> None:
        client = client_with(FakeLLMClient())

        response = await client.post("/assistant/ask", json={"question": ""})

        assert response.status_code == 422

    async def test_returns_422_on_blank_question(self, client_with: ClientFactory) -> None:
        llm_client = FakeLLMClient()
        client = client_with(llm_client)

        response = await client.post("/assistant/ask", json={"question": "   "})

        assert response.status_code == 422
        assert "question" in response.json()["detail"]
        assert llm_client.requests == []

    async def test_returns_422_on_unknown_field(self, client_with: ClientFactory) -> None:
        client = client_with(FakeLLMClient())

        response = await client.post(
            "/assistant/ask", json={"question": "What is a widget?", "extra": 1}
        )

        assert response.status_code == 422

    async def test_c8_returns_200_with_fallback_when_llm_unavailable(
        self, client_with: ClientFactory
    ) -> None:
        client = client_with(FakeLLMClient(fail=True))

        response = await client.post("/assistant/ask", json={"question": "What is a widget?"})

        assert response.status_code == 200
        body = response.json()
        assert body["fallback_used"] is True
        assert body["usage"] is None
        assert body["sources"] == [_source_json(WIDGET)]
        assert body["text"].startswith(FALLBACK_WITH_SOURCES)


class TestOpenApi:
    def test_c9_assistant_exposes_no_indexing_endpoint(self) -> None:
        paths = create_app().openapi()["paths"]

        assert [path for path in paths if path.startswith("/assistant")] == ["/assistant/ask"]
