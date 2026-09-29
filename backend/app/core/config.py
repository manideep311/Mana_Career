from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Values that must never sign a JWT in any environment: the development sentinel
# that shipped in `.env.example`, and the placeholders people paste from docs.
_PLACEHOLDER_SECRETS = frozenset(
    {"change-me", "changeme", "secret", "jwt-secret", "your-secret", "please-change-me"}
)
_PROD_MIN_SECRET_CHARS = 32


def _is_placeholder_secret(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        not lowered
        or lowered.startswith("dev-only-")
        or "change-me" in lowered
        or "changeme" in lowered
        or lowered in _PLACEHOLDER_SECRETS
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "info"
    api_base_path: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    # Peers allowed to assert the real client address via CF-Connecting-IP
    # (e.g. the docker bridge address a local Cloudflare tunnel connects from).
    trusted_proxy_cidrs: Annotated[list[str], NoDecode] = Field(default_factory=list)

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
    # Hard cap for any request body that is not a résumé upload.
    max_request_body_bytes: int = 1_048_576

    # Only providers with a shipped adapter are accepted: anything else fails at
    # startup instead of inside a worker job.
    llm_provider: Literal["fake", "anthropic"] = "fake"
    anthropic_api_key: SecretStr | None = None

    embeddings_provider: Literal["fake", "voyage"] = "fake"
    embed_model: str = "fake-embed-1"
    voyage_api_key: SecretStr | None = None
    embed_dim: int = 1024

    # "none" disables web research; the agent reports the step as skipped.
    search_provider: Literal["none", "fake", "tavily"] = "none"
    search_api_key: SecretStr | None = None
    doc_render_enabled: bool = True
    email_provider: Literal["console"] = "console"

    file_store: Literal["local"] = "local"
    file_store_local_dir: str = "./var/files"
    resume_max_bytes: int = 10_485_760
    resume_max_pages: int = 15
    resume_parser: Literal["pdfium", "pypdf"] = "pdfium"
    llm_model_extraction: str = "claude-haiku-4-5-20251001"
    anthropic_model_fallback: str = "claude-sonnet-5"

    # Explicit opt-in for a production deployment that runs without live AI
    # providers. The UI reads it from /api/v1/meta and says so.
    demo_mode: bool = False

    @model_validator(mode="after")
    def _validate(self) -> Self:
        # Never echo secret values in these messages.
        if _is_placeholder_secret(self.jwt_secret.get_secret_value()):
            raise ValueError(
                "JWT_SECRET is a placeholder or development value. "
                "Generate one with `openssl rand -hex 32` (or run `just init-env`)."
            )
        if self.llm_provider == "anthropic" and not _has_value(self.anthropic_api_key):
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        if self.embeddings_provider == "voyage" and not _has_value(self.voyage_api_key):
            raise ValueError("VOYAGE_API_KEY is required when EMBEDDINGS_PROVIDER=voyage")
        if self.search_provider == "tavily" and not _has_value(self.search_api_key):
            raise ValueError("SEARCH_API_KEY is required when SEARCH_PROVIDER=tavily")
        if self.env == "prod":
            self._validate_production()
        return self

    def _validate_production(self) -> None:
        if len(self.jwt_secret.get_secret_value()) < _PROD_MIN_SECRET_CHARS:
            raise ValueError(
                f"JWT_SECRET must be at least {_PROD_MIN_SECRET_CHARS} characters in production"
            )
        if not self.refresh_cookie_secure:
            raise ValueError("REFRESH_COOKIE_SECURE must be true in production")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit origins in production")
        fakes = [
            name
            for name, value in (
                ("LLM_PROVIDER", self.llm_provider),
                ("EMBEDDINGS_PROVIDER", self.embeddings_provider),
                ("SEARCH_PROVIDER", self.search_provider),
            )
            if value == "fake"
        ]
        if fakes and not self.demo_mode:
            raise ValueError(
                f"{', '.join(fakes)} use the fake provider. Configure a real provider, "
                "or set DEMO_MODE=true to run a clearly labelled demo."
            )

    @property
    def ai_generation_enabled(self) -> bool:
        """True when a real LLM writes prose (letters, tailored bullets)."""
        return self.llm_provider != "fake"

    @field_validator("cors_origins", "trusted_proxy_cidrs", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def _valid_cidrs(cls, v: list[str]) -> list[str]:
        for cidr in v:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(f"TRUSTED_PROXY_CIDRS entry is not a network: {cidr}") from exc
        return v


def _has_value(secret: SecretStr | None) -> bool:
    return secret is not None and bool(secret.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
