from __future__ import annotations

import httpx
import pytest

from app.domain.agents.search.adapters.tavily import (
    SearchProviderError,
    TavilySearchProvider,
)


@pytest.mark.asyncio
async def test_tavily_maps_sources_and_limits_results() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.org/source",
                        "title": "Company update",
                        "content": "A source snippet.",
                        "published_date": "2026-09-01T00:00:00Z",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        hits = await TavilySearchProvider("test-key", client=client).search("latest news", k=2)

    assert len(hits) == 1
    assert hits[0]["url"] == "https://example.org/source"
    assert hits[0]["published_date"] == "2026-09-01T00:00:00Z"
    assert hits[0]["retrieved_at"].endswith("+00:00")
    request = requests[0]
    assert request.url == "https://api.tavily.com/search"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.read()
    assert b'"max_results":2' in request.content
    assert b'"include_published_date":true' in request.content


@pytest.mark.asyncio
async def test_tavily_retries_rate_limit_then_succeeds() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0.5"})
        return httpx.Response(200, json={"results": []})

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        hits = await TavilySearchProvider(
            "test-key", client=client, sleep=record_sleep
        ).search("query", k=1)

    assert hits == []
    assert attempts == 2
    assert delays == [0.5]


@pytest.mark.asyncio
async def test_tavily_fails_closed_on_provider_error_without_leaking_key() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(401, text="bad key"))
    ) as client:
        provider = TavilySearchProvider("test-key", client=client)
        with pytest.raises(SearchProviderError) as exc:
            await provider.search("query")

    assert "test-key" not in str(exc.value)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_tavily_rejects_malformed_or_unsafe_source_urls() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"results": [{"url": "javascript:alert(1)", "title": "x", "content": "y"}]},
            )
        )
    ) as client:
        with pytest.raises(SearchProviderError):
            await TavilySearchProvider("test-key", client=client).search("query")
