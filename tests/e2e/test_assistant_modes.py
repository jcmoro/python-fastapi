from httpx import ASGITransport, AsyncClient
from main import create_app
from tests.fakes.documents import FakeDocumentSearch
from tests.fakes.embedding_client import FakeEmbeddingClient
from tests.fakes.llm_client import FakeLLMClient

from contexts.assistant.ui.dependencies import (
    get_catalog_agent,
    get_document_search,
    get_embedding_client,
    get_llm_client,
)


async def test_rb1_rag_mode_never_builds_the_agent() -> None:
    get_catalog_agent.cache_clear()
    application = create_app()
    llm, embeddings, search = FakeLLMClient(), FakeEmbeddingClient(), FakeDocumentSearch()
    application.dependency_overrides[get_llm_client] = lambda: llm
    application.dependency_overrides[get_embedding_client] = lambda: embeddings
    application.dependency_overrides[get_document_search] = lambda: search

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.post("/assistant/ask", json={"question": "What is a widget?"})

    assert response.status_code == 200
    assert get_catalog_agent.cache_info().currsize == 0
