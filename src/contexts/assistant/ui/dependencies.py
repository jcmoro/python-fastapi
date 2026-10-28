from functools import lru_cache
from typing import Annotated

from anthropic import AsyncAnthropic
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from contexts.assistant.application.use_cases.ask_assistant import AskAssistant
from contexts.assistant.application.use_cases.index_catalog import IndexCatalog
from contexts.assistant.application.use_cases.recommend_candidate import RecommendCandidate
from contexts.assistant.domain.ports.candidate_assessor import CandidateAssessor
from contexts.assistant.domain.ports.catalog_agent import CatalogAgent
from contexts.assistant.domain.ports.catalog_reader import CatalogReader
from contexts.assistant.domain.ports.document_index import DocumentIndex
from contexts.assistant.domain.ports.document_search import DocumentSearch
from contexts.assistant.domain.ports.embedding_client import EmbeddingClient
from contexts.assistant.domain.ports.llm_client import LLMClient
from contexts.assistant.infrastructure.agent.anthropic_agent_model import AnthropicAgentModel
from contexts.assistant.infrastructure.agent.langgraph_catalog_agent import LangGraphCatalogAgent
from contexts.assistant.infrastructure.agent.tools import build_tools
from contexts.assistant.infrastructure.catalog.list_products_catalog_reader import (
    ListProductsCatalogReader,
)
from contexts.assistant.infrastructure.embeddings.fastembed_embedding_client import (
    FastEmbedEmbeddingClient,
)
from contexts.assistant.infrastructure.llm.anthropic_llm_client import AnthropicLLMClient
from contexts.assistant.infrastructure.llm.claude_candidate_assessor import (
    ClaudeCandidateAssessor,
)
from contexts.assistant.infrastructure.persistence.sqlalchemy_document_index import (
    SqlAlchemyDocumentIndex,
)
from contexts.assistant.infrastructure.persistence.sqlalchemy_document_search import (
    SqlAlchemyDocumentSearch,
)
from contexts.catalog.application.use_cases.get_product import GetProduct
from contexts.catalog.application.use_cases.list_products import ListProducts
from contexts.catalog.ui.dependencies import (
    get_get_product_use_case,
    get_list_products_use_case,
)
from shared.infrastructure.database import get_session, session_factory
from shared.infrastructure.settings import get_settings


@lru_cache
def get_anthropic_client() -> AsyncAnthropic:
    api_key = get_settings().anthropic_api_key
    return AsyncAnthropic(api_key=api_key.get_secret_value() if api_key else None)


@lru_cache
def get_llm_client() -> LLMClient:
    settings = get_settings()
    return AnthropicLLMClient(
        client=get_anthropic_client(),
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    settings = get_settings()
    return FastEmbedEmbeddingClient(
        model_name=settings.embedding_model,
        cache_dir=settings.embedding_cache_dir,
        local_files_only=settings.embedding_local_files_only,
    )


def get_document_search() -> DocumentSearch:
    return SqlAlchemyDocumentSearch(session_factory)


def get_document_index(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentIndex:
    return SqlAlchemyDocumentIndex(session)


def get_catalog_reader(
    list_products: Annotated[ListProducts, Depends(get_list_products_use_case)],
    get_product: Annotated[GetProduct, Depends(get_get_product_use_case)],
) -> CatalogReader:
    return ListProductsCatalogReader(list_products, get_product)


@lru_cache
def get_candidate_assessor() -> CandidateAssessor:
    settings = get_settings()
    return ClaudeCandidateAssessor(
        client=get_anthropic_client(),
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        samples=settings.selector_samples,
        max_tokens=settings.selector_max_tokens,
        max_concurrency=settings.selector_max_concurrency,
    )


def get_recommend_candidate_use_case() -> RecommendCandidate:
    settings = get_settings()
    return RecommendCandidate(
        get_candidate_assessor(),
        top_n=settings.selector_top_n,
        timeout_s=settings.selector_timeout_s,
        requirements_threshold=settings.selector_requirements_threshold,
        min_score=settings.selector_min_score,
    )


@lru_cache
def get_catalog_agent() -> CatalogAgent:
    settings = get_settings()
    model = AnthropicAgentModel(
        client=get_anthropic_client(),
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        max_tokens=settings.llm_max_tokens,
    )
    tools = build_tools(
        embedding_client=get_embedding_client(),
        document_search=get_document_search(),
        recommend_candidate=get_recommend_candidate_use_case(),
        rag_top_k=settings.rag_top_k,
        selector_top_n=settings.selector_top_n,
    )
    return LangGraphCatalogAgent(
        model=model,
        tools=tools,
        embedding_client=get_embedding_client(),
        max_tool_calls=settings.agent_max_tool_calls,
    )


def get_assistant_mode() -> str:
    return get_settings().assistant_mode


def get_mode_catalog_agent(
    mode: Annotated[str, Depends(get_assistant_mode)],
) -> CatalogAgent | None:
    return get_catalog_agent() if mode == "agent" else None


def get_ask_assistant_use_case(
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    document_search: Annotated[DocumentSearch, Depends(get_document_search)],
    agent: Annotated[CatalogAgent | None, Depends(get_mode_catalog_agent)],
) -> AskAssistant:
    settings = get_settings()
    return AskAssistant(
        llm_client,
        embedding_client,
        document_search,
        max_tokens=settings.llm_max_tokens,
        top_k=settings.rag_top_k,
        agent=agent,
    )


def clear_anthropic_dependants() -> None:
    for provider in (get_llm_client, get_candidate_assessor, get_catalog_agent):
        provider.cache_clear()
    get_anthropic_client.cache_clear()


def get_index_catalog_use_case(
    catalog_reader: Annotated[CatalogReader, Depends(get_catalog_reader)],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    document_index: Annotated[DocumentIndex, Depends(get_document_index)],
) -> IndexCatalog:
    return IndexCatalog(catalog_reader, embedding_client, document_index)
