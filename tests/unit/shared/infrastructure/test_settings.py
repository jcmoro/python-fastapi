import pytest
from pydantic import ValidationError

from shared.infrastructure.settings import Settings


class TestRagTopK:
    def test_r4_accepts_up_to_the_hnsw_default_ef_search(self) -> None:
        assert Settings(rag_top_k=40).rag_top_k == 40

    def test_r4_rejects_more_than_the_hnsw_default_ef_search(self) -> None:
        with pytest.raises(ValidationError, match="rag_top_k"):
            Settings(rag_top_k=41)
