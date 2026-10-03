from __future__ import annotations

import ipaddress
import re
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
# Same shape the sign-up form accepts: something@something.tld, no whitespace
# (which also rules out CR/LF header injection).
EMAIL_ADDRESS_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    # Shared with the web app's edge proxy (Vercel): requests carrying it may
    # state the visitor's address, so rate limits see people, not the proxy.
    proxy_shared_secret: SecretStr | None = None

    database_url: str
    # Only the test suite uses this; deployments can leave it unset.
    database_url_test: str | None = None
    redis_url: str
    # Connections per process. Hosted Postgres poolers cap clients (Supabase's
    # free session pooler allows about 15), so small deployments set these low.
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)

    # Run the background worker inside the API process instead of as its own
    # service: one container on hosts whose free plan has no worker type.
    run_worker_in_api: bool = False
    worker_max_jobs: int = Field(default=10, ge=1)

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
    # "console" logs and sends nothing; "smtp" delivers through any SMTP server
    # (a Gmail app password, Brevo, Resend, Postmark, SES, or Mailpit locally).
    email_provider: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = 20.0
    email_from_address: str | None = None
    email_from_name: str = "Mana Career"
    # "redirect" delivers every application email to the applicant's own inbox
    # (safe for a public demo); "live" sends it to the employer.
    email_delivery: Literal["redirect", "live"] = "redirect"
    email_daily_limit_per_user: int = 5
    email_daily_limit_total: int = 100
    # Where the web app lives; account emails link here (reset / verify pages).
    app_base_url: str = "http://localhost:3000"

    # "local" keeps files on a disk the API and worker share; "supabase" keeps
    # them in a private Supabase Storage bucket (for hosts without such a disk).
    file_store: Literal["local", "supabase"] = "local"
    file_store_local_dir: str = "./var/files"
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_storage_bucket: str = "resumes"
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
        if self.file_store == "supabase":
            if not (self.supabase_url or "").startswith("https://"):
                raise ValueError("SUPABASE_URL must be the project's https:// URL")
            if not _has_value(self.supabase_service_role_key):
                raise ValueError(
                    "SUPABASE_SERVICE_ROLE_KEY is required when FILE_STORE=supabase"
                )
        if self.email_provider == "smtp":
            if not (self.smtp_host or "").strip():
                raise ValueError("SMTP_HOST is required when EMAIL_PROVIDER=smtp")
            if not EMAIL_ADDRESS_RE.match((self.email_from_address or "").strip()):
                raise ValueError(
                    "EMAIL_FROM_ADDRESS must be a valid address when EMAIL_PROVIDER=smtp"
                )
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
        if self.proxy_shared_secret is not None and (
            len(self.proxy_shared_secret.get_secret_value().strip()) < _PROD_MIN_SECRET_CHARS
        ):
            raise ValueError(
                f"PROXY_SHARED_SECRET must be at least {_PROD_MIN_SECRET_CHARS} characters "
                "in production"
            )
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit origins in production")
        if self.email_provider == "smtp" and not self.app_base_url.startswith("https://"):
            raise ValueError(
                "APP_BASE_URL must use https in production when email is sent"
            )
        if self.email_provider == "smtp" and self.smtp_security == "none":
            raise ValueError(
                "SMTP_SECURITY=none is only for local test servers, not production"
            )
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

    @field_validator("app_base_url")
    @classmethod
    def _base_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")) or any(c.isspace() for c in v):
            raise ValueError("APP_BASE_URL must start with http:// or https://")
        return v

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
