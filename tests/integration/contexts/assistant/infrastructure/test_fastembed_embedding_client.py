from pathlib import Path

import pytest

from contexts.assistant.infrastructure.embeddings.fastembed_embedding_client import (
    FastEmbedEmbeddingClient,
)

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class TestLocalFilesOnly:
    async def test_r7_fails_instead_of_downloading_when_the_model_is_not_cached(
        self, tmp_path: Path
    ) -> None:
        client = FastEmbedEmbeddingClient(
            model_name=MODEL, cache_dir=str(tmp_path), local_files_only=True
        )

        with pytest.raises(ValueError, match="Could not load model"):
            await client.embed(["hola"])

        assert not any(tmp_path.rglob("*.onnx"))
