"""The client address used for rate limiting and audit logs.

``request.client.host`` is the socket peer, already rewritten by Uvicorn from
nginx's ``X-Forwarded-For`` (Uvicorn trusts only nginx's fixed address). When a
Cloudflare tunnel sits in front of nginx, every visitor arrives from the
tunnel connector, so the real address is in ``CF-Connecting-IP`` — trusted only
when the peer is inside ``TRUSTED_PROXY_CIDRS``. Anyone else sending that
header is ignored.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache

from starlette.requests import Request

from app.core.config import Settings

_CF_HEADER = "cf-connecting-ip"


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


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get(_CF_HEADER, "").strip()
    if forwarded and _is_trusted(peer, tuple(settings.trusted_proxy_cidrs)):
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            return peer
    return peer
