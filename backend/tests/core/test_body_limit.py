"""The request-body guard holds while streaming, with or without Content-Length."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.body_limit import BodySizeLimitMiddleware
from app.core.errors import install_error_handlers

LIMIT = 1_000


def _app(chunks_seen: list[int] | None = None) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        return {"size": len(body)}

    @app.post("/upload")
    async def upload(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    app.add_middleware(
        BodySizeLimitMiddleware, default_limit=LIMIT, route_limits={("POST", "/upload"): 5_000}
    )
    return app


async def _post(app: FastAPI, path: str, **kwargs: object):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.post(path, **kwargs)


async def _stream(
    total: int, chunk: int = 256, sent: list[int] | None = None
) -> AsyncIterator[bytes]:
    remaining = total
    while remaining > 0:
        n = min(chunk, remaining)
        remaining -= n
        if sent is not None:
            sent.append(n)
        yield b"x" * n


async def test_small_body_passes() -> None:
    r = await _post(_app(), "/echo", content=b"x" * 10)
    assert r.status_code == 200 and r.json() == {"size": 10}


async def test_declared_length_over_the_cap_is_rejected_before_reading() -> None:
    r = await _post(_app(), "/echo", content=b"x" * (LIMIT + 1))
    assert r.status_code == 413
    assert r.json()["code"] == "payload_too_large"
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_streamed_body_without_content_length_is_stopped_at_the_cap() -> None:
    sent: list[int] = []
    r = await _post(_app(), "/echo", content=_stream(50 * LIMIT, sent=sent))
    assert r.status_code == 413
    assert r.json()["code"] == "payload_too_large"
    # Stopped shortly after crossing the cap instead of buffering 50x the limit.
    assert sum(sent) < LIMIT + 2 * 256 + 1


async def test_route_specific_limit_for_uploads() -> None:
    ok = await _post(_app(), "/upload", content=b"x" * 4_000)
    assert ok.status_code == 200
    too_big = await _post(_app(), "/upload", content=_stream(6_000))
    assert too_big.status_code == 413


@pytest.fixture
def small_upload_cap(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RESUME_MAX_BYTES", "2048")
    yield
    get_settings.cache_clear()


async def test_real_app_rejects_an_oversized_upload_before_authentication(
    small_upload_cap: None,
) -> None:
    from app.core.body_limit import MULTIPART_OVERHEAD_BYTES
    from app.main import create_app

    async def multipart() -> AsyncIterator[bytes]:
        # A well-formed file part whose content never ends: the parser keeps
        # reading until the guard trips.
        yield (
            b'--x\r\nContent-Disposition: form-data; name="file"; filename="cv.pdf"\r\n'
            b"Content-Type: application/pdf\r\n\r\n"
        )
        async for chunk in _stream(2048 + MULTIPART_OVERHEAD_BYTES + 10_000):
            yield chunk

    body = multipart()
    r = await _post(
        create_app(),
        "/api/v1/resumes",
        content=body,
        headers={"content-type": "multipart/form-data; boundary=x"},
    )
    assert r.status_code == 413
    assert r.json()["code"] == "payload_too_large"
