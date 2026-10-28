import asyncio
import os
from collections.abc import AsyncIterator

import anthropic
import pytest_asyncio
from sqlalchemy import delete, make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.evals.harness import (
    EVAL_DATABASE,
    LOADED_AT,
    ApiCalls,
    ClientFactory,
    Dataset,
    EvalCatalog,
    load_dataset,
)

from contexts.assistant.application.use_cases.index_catalog import IndexCatalog
from contexts.assistant.domain.ports.embedding_client import EmbeddingClient
from contexts.assistant.infrastructure.catalog.list_products_catalog_reader import (
    ListProductsCatalogReader,
)
from contexts.assistant.infrastructure.embeddings.fastembed_embedding_client import (
    FastEmbedEmbeddingClient,
)
from contexts.assistant.infrastructure.persistence.models import ProductDocumentModel
from contexts.assistant.infrastructure.persistence.sqlalchemy_document_index import (
    SqlAlchemyDocumentIndex,
)
from contexts.assistant.infrastructure.persistence.sqlalchemy_document_search import (
    SqlAlchemyDocumentSearch,
)
from contexts.catalog.application.use_cases.get_product import GetProduct
from contexts.catalog.application.use_cases.list_products import ListProducts
from contexts.catalog.domain.product import Product
from contexts.catalog.infrastructure.persistence.models import ProductModel
from contexts.catalog.infrastructure.persistence.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from shared.infrastructure.settings import Settings, get_settings


@pytest_asyncio.fixture(scope="session")
async def settings() -> Settings:
    return get_settings()


@pytest_asyncio.fixture(scope="session")
async def eval_catalog(settings: Settings) -> AsyncIterator[EvalCatalog]:
    admin_url = settings.test_database_url
    eval_url = make_url(admin_url).set(database=EVAL_DATABASE).render_as_string(False)
    await _ensure_database(admin_url)
    await _migrate(eval_url)

    dataset = load_dataset()
    embeddings = FastEmbedEmbeddingClient(
        model_name=settings.embedding_model,
        cache_dir=settings.embedding_cache_dir,
        local_files_only=settings.embedding_local_files_only,
    )
    engine = create_async_engine(eval_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    indexed = await _load(factory, dataset, embeddings)
    yield EvalCatalog(
        dataset=dataset,
        embeddings=embeddings,
        search=SqlAlchemyDocumentSearch(factory),
        indexed=indexed,
    )
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def anthropic_clients() -> AsyncIterator[ClientFactory]:
    clients: list[anthropic.AsyncAnthropic] = []
    api_key = get_settings().anthropic_api_key

    def _factory() -> tuple[anthropic.AsyncAnthropic, ApiCalls]:
        calls = ApiCalls()
        client = anthropic.AsyncAnthropic(
            api_key=api_key.get_secret_value() if api_key else None,
            http_client=anthropic.DefaultAsyncHttpxClient(
                event_hooks={"request": [calls.on_request], "response": [calls.on_response]}
            ),
        )
        clients.append(client)
        return client, calls

    yield _factory
    for client in clients:
        await client.close()


async def _ensure_database(admin_url: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        found = await connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": EVAL_DATABASE}
        )
        if found is None:
            await connection.execute(text(f'CREATE DATABASE "{EVAL_DATABASE}"'))
    await engine.dispose()


async def _migrate(url: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "alembic", "upgrade", "head", env={**os.environ, "DATABASE_URL": url}
    )
    assert await process.wait() == 0, "alembic upgrade failed on the eval database"


async def _load(
    factory: async_sessionmaker[AsyncSession], dataset: Dataset, embeddings: EmbeddingClient
) -> int:
    async with factory() as session:
        await session.execute(delete(ProductDocumentModel))
        await session.execute(delete(ProductModel))
        repository = SqlAlchemyProductRepository(session)
        for item in dataset.products:
            await repository.add(
                Product.create(
                    sku=item.sku,
                    name=item.name,
                    price_cents=item.price_cents,
                    currency=item.currency,
                    product_id=item.product_id,
                    created_at=LOADED_AT,
                )
            )
        reader = ListProductsCatalogReader(ListProducts(repository), GetProduct(repository))
        report = await IndexCatalog(reader, embeddings, SqlAlchemyDocumentIndex(session)).execute()
        await session.commit()
    return report.indexed
