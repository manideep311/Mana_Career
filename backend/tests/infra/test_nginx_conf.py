"""Static checks on deploy/nginx/nginx.conf (the live headers are smoke-tested)."""

from __future__ import annotations

import re
from pathlib import Path

CONF = (Path(__file__).resolve().parents[3] / "deploy" / "nginx" / "nginx.conf").read_text(
    encoding="utf-8"
)

REQUIRED_HEADERS = (
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)


def _https_server_block() -> str:
    start = CONF.index("listen 443 ssl;")
    return CONF[start:]


def test_versions_are_not_advertised() -> None:
    assert re.search(r"^\s*server_tokens off;", CONF, re.M)
    assert "proxy_hide_header X-Powered-By;" in CONF


def test_https_responses_carry_every_security_header() -> None:
    block = _https_server_block()
    for header in REQUIRED_HEADERS:
        assert re.search(rf'add_header {header} ".+" always;', block), header


def test_no_location_overrides_the_inherited_headers() -> None:
    # nginx replaces (does not merge) inherited add_header directives as soon as
    # a location declares one, which would silently drop the security headers.
    for location in re.finditer(r"location [^{]+\{([^}]*)\}", _https_server_block()):
        assert "add_header" not in location.group(1), location.group(0)


def test_csp_keeps_everything_same_origin() -> None:
    csp = re.search(r'Content-Security-Policy "([^"]+)"', CONF)
    assert csp is not None
    policy = csp.group(1)
    for directive in (
        "default-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
    ):
        assert directive in policy, directive
    assert "http:" not in policy and "*" not in policy
