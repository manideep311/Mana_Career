import pytest
from pydantic import SecretStr

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
