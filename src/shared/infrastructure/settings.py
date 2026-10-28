from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="catalog-api")
    app_version: str = Field(default="0.1.0")
    env: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    database_url: str = Field(
        default="postgresql+asyncpg://catalog:catalog@db:5432/catalog",
        description="SQLAlchemy async URL for the primary database.",
    )
    test_database_url: str = Field(
        default="postgresql+asyncpg://catalog:catalog@db-test:5432/catalog_test",
        description="SQLAlchemy async URL for the integration/e2e test database.",
    )

    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key. When unset, the SDK resolves credentials itself.",
    )
    llm_model: str = Field(
        default="claude-haiku-5-5",
        description="Claude model used by the assistant.",
    )
    llm_timeout_s: float = Field(
        default=30.0,
        gt=0,
        description="Timeout in seconds for each LLM attempt.",
    )
    llm_max_retries: int = Field(
        default=0,
        ge=0,
        description="Retries per LLM request. Wall-clock bound: llm_timeout_s * (retries + 1).",
    )
    llm_max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Maximum output tokens per LLM completion.",
    )

    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="fastembed model used to embed catalog documents and questions.",
    )
    embedding_cache_dir: str | None = Field(
        default=None,
        description="Directory where fastembed caches the model. Unset: fastembed's default.",
    )
    embedding_local_files_only: bool = Field(
        default=False,
        description="Only load the model from the cache, never download it. "
        "The Docker image bakes the model in and sets this to true.",
    )
    assistant_mode: Literal["rag", "agent"] = Field(
        default="rag",
        description="'rag' answers with retrieval + one LLM call; 'agent' runs the tool agent.",
    )
    agent_max_tool_calls: int = Field(
        default=5, ge=1, description="Tool calls per agent run before falling back to RAG mode."
    )
    selector_provider: Literal["claude"] = Field(
        default="claude",
        description="Candidate assessor used by the recommendation tool.",
    )
    selector_top_n: int = Field(
        default=10, ge=1, description="Retrieval results passed to the candidate selector."
    )
    selector_max_concurrency: int = Field(
        default=10, ge=1, description="Assessor API calls in flight at the same time."
    )
    selector_timeout_s: float = Field(
        default=10.0, gt=0, description="Overall deadline for assessing all candidates."
    )
    selector_samples: int = Field(
        default=3, ge=1, description="Self-consistency samples per candidate (Claude assessor)."
    )
    selector_max_tokens: int = Field(
        default=1024, ge=1, description="Output token limit per assessor call."
    )
    selector_requirements_threshold: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Minimum probability of 'meets the explicit requirements' to stay eligible.",
    )
    selector_min_score: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Minimum probability of 'suitable for the use' to recommend a candidate.",
    )
    rag_top_k: int = Field(
        default=5,
        gt=0,
        le=40,
        description="Number of catalog documents retrieved per question. At most 40: the "
        "HNSW index returns up to hnsw.ef_search (default 40) candidates per query.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
