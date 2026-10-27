import asyncio
import threading

from fastembed import TextEmbedding

from contexts.assistant.domain.ports.embedding_client import EmbeddingClient


class FastEmbedEmbeddingClient(EmbeddingClient):
    def __init__(self, model_name: str, cache_dir: str | None, local_files_only: bool) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._local_files_only = local_files_only
        self._model: TextEmbedding | None = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_blocking, texts)

    def _embed_blocking(self, texts: list[str]) -> list[list[float]]:
        model = self._loaded_model()
        return [[float(value) for value in vector] for vector in model.embed(texts)]

    def _loaded_model(self) -> TextEmbedding:
        with self._lock:
            if self._model is None:
                self._model = TextEmbedding(
                    model_name=self._model_name,
                    cache_dir=self._cache_dir,
                    local_files_only=self._local_files_only,
                )
            return self._model
