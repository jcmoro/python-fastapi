import pytest
from fastapi.testclient import TestClient
from main import create_app
from tests.fakes.embedding_client import FakeEmbeddingClient

from contexts.assistant.ui import dependencies, lifespan


@pytest.fixture
def embeddings(monkeypatch: pytest.MonkeyPatch) -> FakeEmbeddingClient:
    fake = FakeEmbeddingClient()
    monkeypatch.setattr(lifespan, "get_embedding_client", lambda: fake)
    return fake


def test_r6_app_loads_the_embedding_model_on_startup(embeddings: FakeEmbeddingClient) -> None:
    with TestClient(create_app(warm_up_models=True)):
        assert embeddings.calls == [[lifespan.WARM_UP_TEXT]]


def test_r6_warm_up_is_off_unless_requested(embeddings: FakeEmbeddingClient) -> None:
    with TestClient(create_app()):
        assert embeddings.calls == []


def test_the_shared_anthropic_client_is_closed_on_shutdown() -> None:
    dependencies.get_anthropic_client.cache_clear()
    client = dependencies.get_anthropic_client()

    with TestClient(create_app()):
        assert client.is_closed() is False

    assert client.is_closed() is True
    assert dependencies.get_anthropic_client() is not client
