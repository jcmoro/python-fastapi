from functools import lru_cache

from pydantic import Field
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
