from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


async def _peer(request: Request) -> JSONResponse:
    return JSONResponse({"host": request.client.host if request.client else None})


@pytest.mark.parametrize(
    ("transport_peer", "x_forwarded_for", "expected_host"),
    [
        ("172.30.0.2", "203.0.113.7", "203.0.113.7"),
        ("172.30.0.3", "198.51.100.9", "172.30.0.3"),
    ],
)
async def test_only_trusted_proxy_can_set_client_address(
    transport_peer: str, x_forwarded_for: str, expected_host: str
) -> None:
    app = ProxyHeadersMiddleware(
        Starlette(routes=[Route("/peer", _peer)]),
        trusted_hosts="172.30.0.2",
    )
    transport = ASGITransport(app=app, client=(transport_peer, 12345))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/peer", headers={"X-Forwarded-For": x_forwarded_for})

    assert response.json() == {"host": expected_host}
