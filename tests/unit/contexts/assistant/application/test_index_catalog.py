from dataclasses import replace
from uuid import uuid4

import pytest
from tests.fakes.documents import FakeCatalogReader, FakeDocumentIndex
from tests.fakes.embedding_client import FakeEmbeddingClient

from contexts.assistant.application.dtos import IndexReportDTO
from contexts.assistant.application.use_cases.index_catalog import IndexCatalog
from contexts.assistant.domain.catalog_product import CatalogProduct
from contexts.assistant.domain.product_document import ProductDocument

MODEL = "fake-model"


def _product(name: str) -> CatalogProduct:
    return CatalogProduct(
        product_id=uuid4(),
        sku=f"SKU-{name.upper()}",
        name=name,
        price_cents=1000,
        currency="EUR",
    )


@pytest.fixture
def catalog() -> FakeCatalogReader:
    return FakeCatalogReader([_product("alpha"), _product("beta"), _product("gamma")])


@pytest.fixture
def embeddings() -> FakeEmbeddingClient:
    return FakeEmbeddingClient()


@pytest.fixture
def index() -> FakeDocumentIndex:
    return FakeDocumentIndex()


@pytest.fixture
def use_case(
    catalog: FakeCatalogReader, embeddings: FakeEmbeddingClient, index: FakeDocumentIndex
) -> IndexCatalog:
    return IndexCatalog(catalog, embeddings, index)


class TestExecute:
    async def test_c1_indexes_every_product_into_an_empty_index(
        self,
        use_case: IndexCatalog,
        catalog: FakeCatalogReader,
        embeddings: FakeEmbeddingClient,
        index: FakeDocumentIndex,
    ) -> None:
        report = await use_case.execute()

        assert report == IndexReportDTO(indexed=3, unchanged=0, deleted=0)
        assert set(index.documents) == {p.product_id for p in catalog.products}
        expected = [
            ProductDocument.from_catalog_product(p, embedding_model=MODEL).content
            for p in catalog.products
        ]
        assert embeddings.calls == [expected]

    async def test_c2_second_run_without_changes_embeds_nothing(
        self, use_case: IndexCatalog, embeddings: FakeEmbeddingClient
    ) -> None:
        await use_case.execute()
        embeddings.calls.clear()

        report = await use_case.execute()

        assert report == IndexReportDTO(indexed=0, unchanged=3, deleted=0)
        assert embeddings.calls == []

    async def test_c3_only_the_changed_product_is_embedded_again(
        self,
        use_case: IndexCatalog,
        catalog: FakeCatalogReader,
        embeddings: FakeEmbeddingClient,
        index: FakeDocumentIndex,
    ) -> None:
        await use_case.execute()
        embeddings.calls.clear()
        renamed = replace(catalog.products[1], name="beta v2")
        catalog.products[1] = renamed

        report = await use_case.execute()

        assert report == IndexReportDTO(indexed=1, unchanged=2, deleted=0)
        new_content = ProductDocument.from_catalog_product(renamed, embedding_model=MODEL).content
        assert embeddings.calls == [[new_content]]
        assert index.documents[renamed.product_id].document.content == new_content

    async def test_c4_deletes_documents_of_products_no_longer_in_the_catalog(
        self,
        use_case: IndexCatalog,
        catalog: FakeCatalogReader,
        embeddings: FakeEmbeddingClient,
        index: FakeDocumentIndex,
    ) -> None:
        await use_case.execute()
        embeddings.calls.clear()
        removed = catalog.products.pop(0)

        report = await use_case.execute()

        assert report == IndexReportDTO(indexed=0, unchanged=2, deleted=1)
        assert removed.product_id not in index.documents
        assert set(index.documents) == {p.product_id for p in catalog.products}
        assert embeddings.calls == []

    async def test_empty_catalog_and_empty_index_do_nothing(
        self, embeddings: FakeEmbeddingClient, index: FakeDocumentIndex
    ) -> None:
        use_case = IndexCatalog(FakeCatalogReader(), embeddings, index)

        report = await use_case.execute()

        assert report == IndexReportDTO(indexed=0, unchanged=0, deleted=0)
        assert embeddings.calls == []
        assert index.documents == {}


class TestReviewFixes:
    async def test_r1_keeps_a_product_that_exists_but_was_not_listed(
        self, embeddings: FakeEmbeddingClient, index: FakeDocumentIndex
    ) -> None:
        listed, skipped = _product("listed"), _product("skipped")
        catalog = FakeCatalogReader([listed, skipped])
        await IndexCatalog(catalog, embeddings, index).execute()
        catalog.products, catalog.unlisted = [listed], [skipped]

        report = await IndexCatalog(catalog, embeddings, index).execute()

        assert report.deleted == 0
        assert skipped.product_id in index.documents

    async def test_r1_still_deletes_a_product_that_no_longer_exists(
        self, embeddings: FakeEmbeddingClient, index: FakeDocumentIndex
    ) -> None:
        kept, removed = _product("kept"), _product("removed")
        catalog = FakeCatalogReader([kept, removed])
        await IndexCatalog(catalog, embeddings, index).execute()
        catalog.products = [kept]

        report = await IndexCatalog(catalog, embeddings, index).execute()

        assert report.deleted == 1
        assert removed.product_id not in index.documents

    async def test_r2_changing_the_embedding_model_reembeds_everything(
        self, use_case: IndexCatalog, embeddings: FakeEmbeddingClient
    ) -> None:
        await use_case.execute()
        embeddings.calls.clear()
        embeddings.current_model_name = "another-model"

        report = await use_case.execute()

        assert report == IndexReportDTO(indexed=3, unchanged=0, deleted=0)
        assert len(embeddings.calls[0]) == 3

    async def test_r3_embeds_and_upserts_in_batches(
        self, embeddings: FakeEmbeddingClient, index: FakeDocumentIndex
    ) -> None:
        catalog = FakeCatalogReader([_product(f"p{i}") for i in range(5)])
        use_case = IndexCatalog(catalog, embeddings, index, batch_size=2)

        report = await use_case.execute()

        assert report.indexed == 5
        assert [len(call) for call in embeddings.calls] == [2, 2, 1]
        assert index.upsert_sizes == [2, 2, 1]


class TestReadModelColumns:
    async def test_a7_reindexes_documents_missing_catalog_columns(
        self,
        use_case: IndexCatalog,
        catalog: FakeCatalogReader,
        embeddings: FakeEmbeddingClient,
        index: FakeDocumentIndex,
    ) -> None:
        await use_case.execute()
        embeddings.calls.clear()
        incomplete = catalog.products[0]
        index.incomplete.add(incomplete.product_id)

        report = await use_case.execute()

        assert report == IndexReportDTO(indexed=1, unchanged=2, deleted=0)
        expected = ProductDocument.from_catalog_product(incomplete, embedding_model=MODEL)
        assert embeddings.calls == [[expected.content]]
        assert index.incomplete == set()

    async def test_a8_a_reused_sku_does_not_break_the_reindex(
        self, embeddings: FakeEmbeddingClient, index: FakeDocumentIndex
    ) -> None:
        original = _product("reused")
        catalog = FakeCatalogReader([original])
        await IndexCatalog(catalog, embeddings, index).execute()
        replacement = replace(original, product_id=uuid4(), name="reused v2")
        catalog.products = [replacement]

        report = await IndexCatalog(catalog, embeddings, index).execute()

        assert report == IndexReportDTO(indexed=1, unchanged=0, deleted=1)
        assert set(index.documents) == {replacement.product_id}
