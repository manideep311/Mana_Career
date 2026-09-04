from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "info"
    api_base_path: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    database_url: str
    database_url_test: str
    redis_url: str

    jwt_secret: SecretStr
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 2_592_000

    refresh_cookie_name: str = "mana_refresh"
    refresh_cookie_secure: bool = True

    rate_limit_default_per_minute: int = 240
    upload_limit_per_hour: int = 20
    llm_limit_per_hour: int = 60

    llm_provider: Literal["fake", "anthropic", "openai", "gemini"] = "fake"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

    embeddings_provider: Literal["fake", "voyage", "openai", "local"] = "fake"
    embed_model: str = "fake-embed-1"
    voyage_api_key: SecretStr | None = None
    embed_dim: int = 1024

    search_provider: Literal["fake", "tavily", "brave"] = "fake"
    search_api_key: SecretStr | None = None

    file_store: Literal["local", "s3"] = "local"
    file_store_local_dir: str = "./var/files"
    resume_max_bytes: int = 10_485_760
    resume_max_pages: int = 15
    llm_model_extraction: str = "claude-haiku-4-5-20251001"
    anthropic_model_fallback: str = "claude-sonnet-5"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
