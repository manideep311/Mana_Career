import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import (
    AIPausedError,
    AIUnavailableError,
    AppError,
    NotFoundError,
    RateLimitedError,
    install_error_handlers,
    to_problem,
)


def test_to_problem_shape():
    p = to_problem(NotFoundError(detail="resume 7 not found"), instance="/api/v1/resumes/7")
    assert p == {
        "type": "about:blank",
        "title": "Not found",
        "status": 404,
        "detail": "resume 7 not found",
        "instance": "/api/v1/resumes/7",
        "code": "not_found",
    }


@pytest.fixture
def client() -> AsyncClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppError(detail="kaboom")

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError(detail="nope")

    @app.get("/slow")
    async def slow() -> None:
        raise RateLimitedError(retry_after=30)

    @app.get("/ai-busy")
    async def ai_busy() -> None:
        raise AIUnavailableError(retry_after=12)

    @app.get("/ai-paused")
    async def ai_paused() -> None:
        raise AIPausedError()

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_apperror_becomes_problem_json(client: AsyncClient):
    r = await client.get("/boom")
    assert r.status_code == 500
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "internal_error"


async def test_notfound_status_and_code(client: AsyncClient):
    r = await client.get("/missing")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


async def test_rate_limited_sets_retry_after_header(client: AsyncClient):
    r = await client.get("/slow")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "30"
    assert r.json()["code"] == "rate_limited"


def test_code_override_flows_into_problem():
    p = to_problem(AppError(detail="dup", code="email_taken"), instance="/x")
    assert p["code"] == "email_taken"
    assert p["status"] == 500  # class default preserved


def test_code_defaults_to_class_attr():
    assert to_problem(NotFoundError(), instance="/x")["code"] == "not_found"


async def test_busy_ai_quota_reads_plainly_with_retry_after(client: AsyncClient):
    r = await client.get("/ai-busy")
    assert r.status_code == 503
    assert r.headers["retry-after"] == "12"
    body = r.json()
    assert body["code"] == "ai_busy"
    assert body["title"] == "The free AI quota is busy, try again shortly"
    assert body["detail"] is None  # never the upstream response


async def test_paused_ai_says_why(client: AsyncClient):
    r = await client.get("/ai-paused")
    assert r.status_code == 503
    assert "retry-after" not in r.headers
    assert r.json()["code"] == "ai_paused"
    assert "paused for today" in r.json()["title"]
    # The worker's agent nodes surface str(exc): it must be the plain title.
    assert str(AIPausedError()) == AIPausedError.title
