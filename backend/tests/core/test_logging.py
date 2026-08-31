import json

import pytest
import structlog

from app.core.config import Settings
from app.core.logging import (
    configure_logging,
    current_request_id,
    get_logger,
    redact_secrets,
)


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Keep global structlog config from leaking into other test modules."""
    yield
    structlog.reset_defaults()


@pytest.fixture
def prod_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k, v in {
        "DATABASE_URL": "x", "DATABASE_URL_TEST": "x", "REDIS_URL": "x",
        "JWT_SECRET": "x", "ENV": "prod",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_redacts_known_keys():
    out = redact_secrets(None, None, {"event": "login", "password": "hunter2", "user": "amy"})
    assert out["password"] == "***"
    assert out["user"] == "amy"


def test_redacts_secret_shaped_values():
    out = redact_secrets(None, None, {"event": "call", "header": "Bearer abc.def.ghi123456789"})
    assert out["header"] == "***"


def test_json_output_in_prod(prod_settings: Settings, capsys: pytest.CaptureFixture[str]):
    configure_logging(prod_settings)
    get_logger("test").info("hello", api_key="sk-secret-value-1234567890")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "hello"
    assert record["api_key"] == "***"
    assert record["level"] == "info"


def test_current_request_id_none_outside_request():
    structlog.contextvars.clear_contextvars()
    assert current_request_id() is None


def test_current_request_id_reads_bound_value():
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="req-42")
    try:
        assert current_request_id() == "req-42"
    finally:
        structlog.contextvars.clear_contextvars()
