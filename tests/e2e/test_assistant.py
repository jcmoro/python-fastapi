from collections.abc import AsyncIterator, Callable

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from main import create_app
from tests.fakes.llm_client import FakeLLMClient

from contexts.assistant.domain.completion import Completion
from contexts.assistant.ui.dependencies import get_llm_client

ClientFactory = Callable[[FakeLLMClient], AsyncClient]


@pytest_asyncio.fixture
async def client_with() -> AsyncIterator[ClientFactory]:
    clients: list[AsyncClient] = []

    def _factory(llm_client: FakeLLMClient) -> AsyncClient:
        application = create_app()
        application.dependency_overrides[get_llm_client] = lambda: llm_client
        client = AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver")
        clients.append(client)
        return client

    yield _factory
    for client in clients:
        await client.aclose()


class TestAsk:
    async def test_returns_200_with_answer_and_usage(self, client_with: ClientFactory) -> None:
        completion = Completion(
            text="Widgets are small devices.",
            model="claude-test",
            input_tokens=50,
            output_tokens=6,
            latency_ms=120,
        )
        client = client_with(FakeLLMClient(completion))

        response = await client.post("/assistant/ask", json={"question": "What is a widget?"})

        assert response.status_code == 200
        assert response.json() == {
            "text": "Widgets are small devices.",
            "usage": {
                "model": "claude-test",
                "input_tokens": 50,
                "output_tokens": 6,
                "latency_ms": 120,
            },
        }

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

    async def test_returns_503_when_llm_unavailable(self, client_with: ClientFactory) -> None:
        client = client_with(FakeLLMClient(fail=True))

        response = await client.post("/assistant/ask", json={"question": "What is a widget?"})

        assert response.status_code == 503
        assert response.json() == {"detail": "the language model is unavailable"}
