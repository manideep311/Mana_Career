"""Deployment metadata and API-docs exposure (no database needed)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


async def _get(path: str) -> tuple[int, dict[str, object] | None]:
    from app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    body = response.json() if response.headers.get("content-type", "").startswith(
        "application/json"
    ) else None
    return response.status_code, body


async def test_meta_reports_demo_capabilities(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("LLM_PROVIDER", "fake")
    settings_env.setenv("SEARCH_PROVIDER", "none")
    settings_env.setenv("DEMO_MODE", "true")
    status, body = await _get("/api/v1/meta")
    assert status == 200
    assert body == {
        "demo_mode": True, "ai_writing": False, "web_research": False,
        "email_delivery": "console",
    }


async def test_meta_reports_where_application_emails_go(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("EMAIL_PROVIDER", "smtp")
    settings_env.setenv("SMTP_HOST", "smtp.example.com")
    settings_env.setenv("EMAIL_FROM_ADDRESS", "applications@example.com")
    settings_env.setenv("EMAIL_DELIVERY", "redirect")
    _status, body = await _get("/api/v1/meta")
    assert body["email_delivery"] == "redirect"
    settings_env.setenv("EMAIL_DELIVERY", "live")
    get_settings.cache_clear()
    _status, body = await _get("/api/v1/meta")
    assert body["email_delivery"] == "live"


async def test_api_schema_is_served_outside_production(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("ENV", "test")
    status, _ = await _get("/api/openapi.json")
    assert status == 200


async def test_api_schema_and_docs_are_hidden_in_production(
    settings_env: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "ENV": "prod",
        "JWT_SECRET": "p" * 40,
        "DEMO_MODE": "true",
        "SEARCH_PROVIDER": "none",
        "REFRESH_COOKIE_SECURE": "true",
    }.items():
        settings_env.setenv(key, value)
    for path in ("/api/openapi.json", "/docs", "/redoc"):
        status, _ = await _get(path)
        assert status == 404, path
