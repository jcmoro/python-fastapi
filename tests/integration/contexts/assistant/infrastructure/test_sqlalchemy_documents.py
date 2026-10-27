from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contexts.assistant.domain.product_document import EmbeddedDocument, ProductDocument
from contexts.assistant.infrastructure.persistence.models import EMBEDDING_DIMENSIONS
from contexts.assistant.infrastructure.persistence.sqlalchemy_document_index import (
    SqlAlchemyDocumentIndex,
)
from contexts.assistant.infrastructure.persistence.sqlalchemy_document_search import (
    SqlAlchemyDocumentSearch,
)


def _vector(*weights: tuple[int, float]) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for position, value in weights:
        vector[position] = value
    return vector


def _embedded(
    content: str, vector: list[float], product_id: UUID | None = None
) -> EmbeddedDocument:
    return EmbeddedDocument(
        document=ProductDocument(
            product_id=product_id or uuid4(), content=content, content_hash=f"hash-{content}"
        ),
        embedding=vector,
    )


@pytest.fixture
def index(db_session: AsyncSession) -> SqlAlchemyDocumentIndex:
    return SqlAlchemyDocumentIndex(db_session)


@pytest.fixture
def search(db_session: AsyncSession) -> SqlAlchemyDocumentSearch:
    factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    return SqlAlchemyDocumentSearch(factory)


class TestDocumentIndex:
    async def test_upsert_inserts_and_reports_hashes(self, index: SqlAlchemyDocumentIndex) -> None:
        first = _embedded("alpha", _vector((0, 1.0)))
        second = _embedded("beta", _vector((1, 1.0)))

        await index.upsert([first, second])

        assert await index.content_hashes() == {
            first.document.product_id: "hash-alpha",
            second.document.product_id: "hash-beta",
        }

    async def test_upsert_replaces_an_existing_document(
        self, index: SqlAlchemyDocumentIndex, search: SqlAlchemyDocumentSearch
    ) -> None:
        product_id = uuid4()
        await index.upsert([_embedded("old", _vector((0, 1.0)), product_id)])

        await index.upsert([_embedded("new", _vector((1, 1.0)), product_id)])

        assert await index.content_hashes() == {product_id: "hash-new"}
        [hit] = await search.search(_vector((1, 1.0)), k=1)
        assert hit.product_id == product_id
        assert hit.content == "new"

    async def test_c4_delete_removes_only_the_given_documents(
        self, index: SqlAlchemyDocumentIndex
    ) -> None:
        kept = _embedded("kept", _vector((0, 1.0)))
        orphan = _embedded("orphan", _vector((1, 1.0)))
        await index.upsert([kept, orphan])

        await index.delete([orphan.document.product_id])

        assert await index.content_hashes() == {kept.document.product_id: "hash-kept"}

    async def test_delete_ignores_ids_that_are_not_indexed(
        self, index: SqlAlchemyDocumentIndex
    ) -> None:
        kept = _embedded("kept", _vector((0, 1.0)))
        await index.upsert([kept])

        await index.delete([uuid4()])

        assert await index.content_hashes() == {kept.document.product_id: "hash-kept"}


class TestDocumentSearch:
    async def test_c10_returns_the_nearest_document_first(
        self, index: SqlAlchemyDocumentIndex, search: SqlAlchemyDocumentSearch
    ) -> None:
        near = _embedded("near", _vector((0, 1.0), (1, 0.1)))
        middle = _embedded("middle", _vector((0, 1.0), (1, 1.0)))
        far = _embedded("far", _vector((1, 1.0)))
        await index.upsert([far, near, middle])

        results = await search.search(_vector((0, 1.0)), k=3)

        assert [r.content for r in results] == ["near", "middle", "far"]
        assert results[0].score == pytest.approx(0.995, abs=1e-3)
        assert results[0].score > results[1].score > results[2].score

    async def test_limits_results_to_k(
        self, index: SqlAlchemyDocumentIndex, search: SqlAlchemyDocumentSearch
    ) -> None:
        await index.upsert(
            [_embedded(name, _vector((i, 1.0))) for i, name in enumerate(["a", "b", "c"])]
        )

        assert len(await search.search(_vector((0, 1.0)), k=2)) == 2

    async def test_empty_index_returns_no_results(self, search: SqlAlchemyDocumentSearch) -> None:
        assert await search.search(_vector((0, 1.0)), k=5) == []
