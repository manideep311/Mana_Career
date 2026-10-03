import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings


def _env(**over: str) -> dict[str, str]:
    base = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
        "DATABASE_URL_TEST": "postgresql+asyncpg://u:p@h/db_test",
        "REDIS_URL": "redis://h:6379/0",
        "JWT_SECRET": "s3cr3t",
    }
    base.update(over)
    return base


def test_loads_from_env(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env(ENV="dev", EMBED_DIM="1024").items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.env == "dev"
    assert s.embed_dim == 1024
    assert s.llm_provider == "fake"


def test_secret_fields_are_not_plaintext_in_repr(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert isinstance(s.jwt_secret, SecretStr)
    assert "s3cr3t" not in repr(s)
    assert s.jwt_secret.get_secret_value() == "s3cr3t"


def test_cors_origins_parsed_as_list(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env(CORS_ORIGINS="http://a.com,http://b.com").items():
        monkeypatch.setenv(k, v)
    assert Settings().cors_origins == ["http://a.com", "http://b.com"]


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    assert get_settings() is get_settings()


def test_refresh_cookie_defaults(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    # conftest sets REFRESH_COOKIE_SECURE=false process-wide for the test client;
    # this test checks the code default, so clear the ambient value first.
    monkeypatch.delenv("REFRESH_COOKIE_SECURE", raising=False)
    s = Settings()
    assert s.refresh_cookie_name == "mana_refresh"
    assert s.refresh_cookie_secure is True


def test_refresh_cookie_secure_env_override(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env(REFRESH_COOKIE_SECURE="false").items():
        monkeypatch.setenv(k, v)
    assert Settings().refresh_cookie_secure is False


def test_resume_and_filestore_defaults(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.file_store == "local"
    assert s.file_store_local_dir == "./var/files"
    assert s.resume_max_bytes == 10_485_760
    assert s.resume_max_pages == 15
    assert s.llm_model_extraction == "claude-haiku-4-5-20251001"
    assert s.upload_limit_per_hour == 20

_PROD_OK = {
    "ENV": "prod",
    "JWT_SECRET": "p" * 40,
    "LLM_PROVIDER": "anthropic",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "EMBEDDINGS_PROVIDER": "voyage",
    "VOYAGE_API_KEY": "test-voyage-key",
    "SEARCH_PROVIDER": "none",
    "REFRESH_COOKIE_SECURE": "true",
    "CORS_ORIGINS": "https://career.example",
}


def _apply(monkeypatch: pytest.MonkeyPatch, **over: str) -> None:
    for key in (
        "SEARCH_PROVIDER", "DEMO_MODE", "ANTHROPIC_API_KEY", "VOYAGE_API_KEY",
        "EMAIL_PROVIDER", "SMTP_HOST", "SMTP_SECURITY", "EMAIL_FROM_ADDRESS", "EMAIL_DELIVERY",
        "APP_BASE_URL", "FILE_STORE", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
        "PROXY_SHARED_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in _env(**over).items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("env", ["dev", "test", "prod"])
@pytest.mark.parametrize(
    "secret", ["dev-only-change-me", "dev-only-anything", "change-me", "CHANGEME", "secret", "  "]
)
def test_placeholder_jwt_secret_rejected_in_every_environment(
    monkeypatch: pytest.MonkeyPatch, env: str, secret: str
):
    _apply(monkeypatch, **{**_PROD_OK, "ENV": env, "JWT_SECRET": secret})
    with pytest.raises(ValidationError, match="JWT_SECRET") as exc:
        Settings()
    if secret.strip():
        assert secret not in str(exc.value)


def test_prod_rejects_short_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    secret = "k" * 31
    _apply(monkeypatch, **{**_PROD_OK, "JWT_SECRET": secret})
    with pytest.raises(ValidationError, match="at least 32") as exc:
        Settings()
    assert secret not in str(exc.value)


def test_prod_accepts_a_complete_configuration(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, **_PROD_OK)
    s = Settings()
    assert s.env == "prod" and s.ai_generation_enabled and not s.demo_mode


def test_prod_rejects_insecure_refresh_cookie(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, **{**_PROD_OK, "REFRESH_COOKIE_SECURE": "false"})
    with pytest.raises(ValidationError, match="REFRESH_COOKIE_SECURE"):
        Settings()


def test_prod_rejects_wildcard_cors(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, **{**_PROD_OK, "CORS_ORIGINS": "*"})
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings()


def test_prod_rejects_fake_providers_without_demo_mode(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, **{**_PROD_OK, "LLM_PROVIDER": "fake", "EMBEDDINGS_PROVIDER": "fake"})
    with pytest.raises(ValidationError, match="DEMO_MODE") as exc:
        Settings()
    assert "LLM_PROVIDER" in str(exc.value) and "EMBEDDINGS_PROVIDER" in str(exc.value)


def test_prod_demo_mode_is_an_explicit_opt_in(monkeypatch: pytest.MonkeyPatch):
    _apply(
        monkeypatch,
        **{**_PROD_OK, "LLM_PROVIDER": "fake", "EMBEDDINGS_PROVIDER": "fake", "DEMO_MODE": "true"},
    )
    s = Settings()
    assert s.demo_mode and not s.ai_generation_enabled


def test_prod_does_not_require_web_search(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, **{**_PROD_OK, "SEARCH_PROVIDER": "none"})
    assert Settings().search_provider == "none"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("LLM_PROVIDER", "openai"),
        ("LLM_PROVIDER", "gemini"),
        ("EMBEDDINGS_PROVIDER", "openai"),
        ("EMBEDDINGS_PROVIDER", "local"),
        ("SEARCH_PROVIDER", "brave"),
        ("FILE_STORE", "s3"),
        ("EMAIL_PROVIDER", "sendgrid"),
        ("EMAIL_DELIVERY", "everyone"),
    ],
)
def test_unimplemented_providers_fail_at_startup(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
):
    _apply(monkeypatch, **{key: value})
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    ("provider", "key_var"),
    [
        ("LLM_PROVIDER=anthropic", "ANTHROPIC_API_KEY"),
        ("EMBEDDINGS_PROVIDER=voyage", "VOYAGE_API_KEY"),
    ],
)
def test_real_providers_require_their_key(
    monkeypatch: pytest.MonkeyPatch, provider: str, key_var: str
):
    name, value = provider.split("=")
    _apply(monkeypatch, **{name: value})
    with pytest.raises(ValidationError, match=key_var):
        Settings()


def test_trusted_proxy_cidrs_parsed_and_validated(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, TRUSTED_PROXY_CIDRS="172.30.0.0/24, 127.0.0.1/32")
    assert Settings().trusted_proxy_cidrs == ["172.30.0.0/24", "127.0.0.1/32"]
    _apply(monkeypatch, TRUSTED_PROXY_CIDRS="not-a-network")
    with pytest.raises(ValidationError, match="TRUSTED_PROXY_CIDRS"):
        Settings()


_SMTP = {
    "EMAIL_PROVIDER": "smtp",
    "SMTP_HOST": "smtp.example.com",
    "EMAIL_FROM_ADDRESS": "applications@example.com",
}


def test_smtp_needs_a_host_and_a_from_address(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, **{**_SMTP, "SMTP_HOST": " "})
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        Settings()
    _apply(monkeypatch, **{**_SMTP, "EMAIL_FROM_ADDRESS": "not-an-address"})
    with pytest.raises(ValidationError, match="EMAIL_FROM_ADDRESS"):
        Settings()


def test_smtp_defaults_are_safe(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, **_SMTP)
    s = Settings()
    assert s.email_provider == "smtp"
    assert s.smtp_port == 587 and s.smtp_security == "starttls"
    assert s.email_delivery == "redirect"  # real employers only on an explicit opt-in
    assert s.email_daily_limit_per_user == 5 and s.email_daily_limit_total == 100


def test_prod_refuses_unencrypted_smtp(monkeypatch: pytest.MonkeyPatch):
    https = {"APP_BASE_URL": "https://career.example"}
    _apply(monkeypatch, **{**_PROD_OK, **_SMTP, **https, "SMTP_SECURITY": "none"})
    with pytest.raises(ValidationError, match="SMTP_SECURITY"):
        Settings()
    _apply(monkeypatch, **{**_PROD_OK, **_SMTP, **https, "SMTP_SECURITY": "starttls"})
    assert Settings().email_provider == "smtp"



def test_app_base_url_is_normalised_and_validated(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, APP_BASE_URL="https://career.example/")
    assert Settings().app_base_url == "https://career.example"
    _apply(monkeypatch, APP_BASE_URL="career.example")
    with pytest.raises(ValidationError, match="APP_BASE_URL"):
        Settings()


def test_prod_email_links_must_be_https(monkeypatch: pytest.MonkeyPatch):
    # Only when real email goes out: links in logged (console) mail don't matter.
    _apply(monkeypatch, **{**_PROD_OK, "APP_BASE_URL": "http://career.example"})
    assert Settings().app_base_url == "http://career.example"
    _apply(monkeypatch, **{**_PROD_OK, **_SMTP, "APP_BASE_URL": "http://career.example"})
    with pytest.raises(ValidationError, match="APP_BASE_URL"):
        Settings()
    _apply(monkeypatch, **{**_PROD_OK, **_SMTP, "APP_BASE_URL": "https://career.example"})
    assert Settings().app_base_url == "https://career.example"


def test_supabase_storage_needs_the_project_url_and_service_key(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, FILE_STORE="supabase")
    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        Settings()
    _apply(monkeypatch, FILE_STORE="supabase", SUPABASE_URL="https://proj.supabase.co")
    with pytest.raises(ValidationError, match="SUPABASE_SERVICE_ROLE_KEY"):
        Settings()
    _apply(
        monkeypatch, FILE_STORE="supabase", SUPABASE_URL="https://proj.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="service-key",
    )
    s = Settings()
    assert s.supabase_storage_bucket == "resumes"
    assert "service-key" not in repr(s)


def test_prod_proxy_secret_must_be_long(monkeypatch: pytest.MonkeyPatch):
    _apply(monkeypatch, **{**_PROD_OK, "PROXY_SHARED_SECRET": "short"})
    with pytest.raises(ValidationError, match="PROXY_SHARED_SECRET") as exc:
        Settings()
    assert "short" not in str(exc.value)
    _apply(monkeypatch, **{**_PROD_OK, "PROXY_SHARED_SECRET": "x" * 40})
    assert Settings().proxy_shared_secret is not None


def test_small_hosts_can_shrink_the_pool_and_run_the_worker_in_the_api(
    monkeypatch: pytest.MonkeyPatch,
):
    _apply(
        monkeypatch, DATABASE_POOL_SIZE="3", DATABASE_MAX_OVERFLOW="2",
        RUN_WORKER_IN_API="true", WORKER_MAX_JOBS="3",
    )
    s = Settings()
    assert (s.database_pool_size, s.database_max_overflow) == (3, 2)
    assert s.run_worker_in_api and s.worker_max_jobs == 3
