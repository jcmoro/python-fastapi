from functools import lru_cache

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
