"""The client address used for rate limiting and audit logs.

``request.client.host`` is the socket peer, already rewritten by Uvicorn from
nginx's ``X-Forwarded-For`` (Uvicorn trusts only nginx's fixed address). When a
Cloudflare tunnel sits in front of nginx, every visitor arrives from the
tunnel connector, so the real address is in ``CF-Connecting-IP`` — trusted only
when the peer is inside ``TRUSTED_PROXY_CIDRS``. Anyone else sending that
header is ignored.

When the web app's edge proxy (Vercel) forwards ``/api`` to the API, every
request arrives from a proxy whose addresses aren't fixed, so a network range
can't vouch for it. Instead the proxy sends ``PROXY_SHARED_SECRET`` with the
visitor's address; the address is believed only when the secret matches.
"""

from __future__ import annotations

import hmac
import ipaddress
from functools import lru_cache

from starlette.requests import Request

from app.core.config import Settings

_CF_HEADER = "cf-connecting-ip"
PROXY_SECRET_HEADER = "x-mana-proxy-secret"  # noqa: S105 - a header name, not a secret
PROXY_CLIENT_HEADER = "x-mana-client-ip"


@lru_cache(maxsize=32)
def _networks(
    cidrs: tuple[str, ...],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


def _is_trusted(peer: str, cidrs: tuple[str, ...]) -> bool:
    if not cidrs:
        return False
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in _networks(cidrs))


def _from_edge_proxy(request: Request, settings: Settings) -> str | None:
    if settings.proxy_shared_secret is None:
        return None
    expected = settings.proxy_shared_secret.get_secret_value().encode()
    sent = request.headers.get(PROXY_SECRET_HEADER, "").encode()
    if not expected or not hmac.compare_digest(sent, expected):
        return None
    try:
        return str(ipaddress.ip_address(request.headers.get(PROXY_CLIENT_HEADER, "").strip()))
    except ValueError:
        return None


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    vouched = _from_edge_proxy(request, settings)
    if vouched is not None:
        return vouched
    forwarded = request.headers.get(_CF_HEADER, "").strip()
    if forwarded and _is_trusted(peer, tuple(settings.trusted_proxy_cidrs)):
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            return peer
    return peer
