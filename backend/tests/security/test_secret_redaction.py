"""Secret redaction in structured logs -- pure, runs everywhere.

Extends tests/core/test_logging.py: proves secret-SHAPED values are masked even
under an innocuous key name, and that a running request never leaks JWT_SECRET.
"""
from __future__ import annotations

import pytest
import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, redact_secrets

_MARK = "***"


def _r(d):
    return redact_secrets(None, None, dict(d))


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Keep a configure_logging() call here from leaking into other modules."""
    yield
    structlog.reset_defaults()


def test_jwt_shaped_value_is_masked():
    assert _r({"ctx": "aaaaaaaaaaaa.bbbbbbbb.cccccccc-1234567890"})["ctx"] == _MARK


def test_argon2_hash_is_masked():
    val = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaGhhc2g"
    assert _r({"h": val})["h"] == _MARK


def test_sk_key_is_masked():
    assert _r({"note": "sk-abcdef0123456789abcdef"})["note"] == _MARK


def test_dsn_password_not_present():
    out = _r({"url": "postgresql+asyncpg://mana:s3cr3tpw@db:5432/mana"})
    assert "s3cr3tpw" not in out["url"]
    assert out["url"] == _MARK


def test_named_keys_masked_regardless_of_shape():
    for key in ("access_token", "refresh_token", "jwt", "database_url", "authorization"):
        assert _r({key: "plainish"})[key] == _MARK


def test_innocuous_pairs_untouched():
    pairs = {"user": "amy", "count": 3, "path": "/api/v1/profile"}
    assert _r(pairs) == pairs


async def test_request_path_never_leaks_jwt_secret(capsys):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    settings: Settings = get_settings()
    configure_logging(settings)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(
        transport=transport, base_url="http://t", headers={"host": "t"}
    ) as client:
        resp = await client.get("/api/v1/profile")

    assert resp.status_code == 401
    assert settings.jwt_secret.get_secret_value() not in capsys.readouterr().out
