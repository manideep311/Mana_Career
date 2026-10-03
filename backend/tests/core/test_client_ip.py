"""Whose address a request counts as (rate limits, audit logs)."""
from __future__ import annotations

from starlette.requests import Request

from app.core.client_ip import PROXY_CLIENT_HEADER, PROXY_SECRET_HEADER, client_ip
from app.core.config import Settings

SECRET = "s" * 40


def _settings(**over) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://x", redis_url="redis://x", jwt_secret="x",
    )
    return Settings(**{**base, **over})


def _request(headers: dict[str, str], peer: str = "10.0.0.7") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 1234),
    })


def test_the_edge_proxy_can_name_the_visitor_with_the_shared_secret():
    req = _request({PROXY_SECRET_HEADER: SECRET, PROXY_CLIENT_HEADER: "203.0.113.9"})
    assert client_ip(req, _settings(proxy_shared_secret=SECRET)) == "203.0.113.9"


def test_without_the_right_secret_the_claim_is_ignored():
    settings = _settings(proxy_shared_secret=SECRET)
    for headers in (
        {PROXY_CLIENT_HEADER: "203.0.113.9"},
        {PROXY_SECRET_HEADER: "wrong", PROXY_CLIENT_HEADER: "203.0.113.9"},
        {PROXY_SECRET_HEADER: SECRET, PROXY_CLIENT_HEADER: "not-an-ip"},
    ):
        assert client_ip(_request(headers), settings) == "10.0.0.7"


def test_no_secret_configured_means_nobody_can_claim_an_address():
    req = _request({PROXY_SECRET_HEADER: "", PROXY_CLIENT_HEADER: "203.0.113.9"})
    assert client_ip(req, _settings()) == "10.0.0.7"
