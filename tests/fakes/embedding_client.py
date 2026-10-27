from contexts.assistant.domain.ports.embedding_client import EmbeddingClient

DEFAULT_VECTOR = [1.0, 0.0, 0.0]


class FakeEmbeddingClient(EmbeddingClient):
    def __init__(
        self, vectors: dict[str, list[float]] | None = None, model_name: str = "fake-model"
    ) -> None:
        self._vectors = vectors or {}
        self.current_model_name = model_name
        self.calls: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return self.current_model_name

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vectors.get(text, DEFAULT_VECTOR) for text in texts]
