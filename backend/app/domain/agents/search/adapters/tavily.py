from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.domain.agents.search.provider import SearchHit, SearchProviderError

__all__ = ["SearchProviderError", "TavilySearchProvider"]

_SEARCH_URL = "https://api.tavily.com/search"
_TIMEOUT_SECONDS = 10.0
_MAX_ATTEMPTS = 3
_MAX_RETRY_AFTER_SECONDS = 2.0


class TavilySearchProvider:
    """Tavily web search adapter with bounded retries and source dates."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Tavily API key must be configured")
        self._api_key = api_key
        self._client = client
        self._sleep = sleep

    async def search(self, query: str, *, k: int = 5) -> list[SearchHit]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("Search query must not be empty")
        if k < 0:
            raise ValueError("Search result count must not be negative")
        if k == 0:
            return []

        payload = {
            "query": cleaned_query[:500],
            "search_depth": "basic",
            "max_results": min(k, 20),
            "topic": "general",
            "include_published_date": True,
            "include_answer": False,
            "include_raw_content": False,
        }

        if self._client is not None:
            response = await self._request(self._client, payload)
        else:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await self._request(client, payload)

        return self._parse_results(response)

    async def _request(
        self, client: httpx.AsyncClient, payload: dict[str, Any]
    ) -> dict[str, Any]:
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await client.post(
                    _SEARCH_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=_TIMEOUT_SECONDS,
                )
            except httpx.TransportError:
                if attempt + 1 == _MAX_ATTEMPTS:
                    raise SearchProviderError("Tavily search transport failed") from None
                await self._sleep(0.25 * (2**attempt))
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 == _MAX_ATTEMPTS:
                    raise SearchProviderError(
                        f"Tavily search unavailable (HTTP {response.status_code})",
                        status_code=response.status_code,
                    )
                await self._sleep(self._retry_delay(response, attempt))
                continue

            if not response.is_success:
                raise SearchProviderError(
                    f"Tavily search request rejected (HTTP {response.status_code})",
                    status_code=response.status_code,
                )

            try:
                result = response.json()
            except ValueError:
                raise SearchProviderError("Tavily returned invalid JSON") from None
            if not isinstance(result, dict):
                raise SearchProviderError("Tavily returned an invalid response")
            return result

        raise SearchProviderError("Tavily search unavailable")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "")
            try:
                return min(max(float(retry_after), 0.0), _MAX_RETRY_AFTER_SECONDS)
            except ValueError:
                pass
        return min(0.25 * (2**attempt), _MAX_RETRY_AFTER_SECONDS)

    @staticmethod
    def _parse_results(response: dict[str, Any]) -> list[SearchHit]:
        results = response.get("results")
        if not isinstance(results, list):
            raise SearchProviderError("Tavily response did not include search results")

        retrieved_at = datetime.now(UTC).isoformat()
        hits: list[SearchHit] = []
        for result in results:
            if not isinstance(result, dict):
                raise SearchProviderError("Tavily returned a malformed search result")
            url = result.get("url")
            title = result.get("title")
            content = result.get("content")
            if (
                not isinstance(url, str)
                or not isinstance(title, str)
                or not isinstance(content, str)
            ):
                raise SearchProviderError("Tavily returned a malformed search result")
            parsed_url = urlsplit(url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise SearchProviderError("Tavily returned an unsafe source URL")
            published_date = result.get("published_date")
            if published_date is not None and not isinstance(published_date, str):
                raise SearchProviderError("Tavily returned an invalid publication date")
            published_date = TavilySearchProvider._normalize_published_date(published_date)
            hits.append(
                {
                    "url": url,
                    "title": title,
                    "content": content,
                    "published_date": published_date,
                    "retrieved_at": retrieved_at,
                }
            )
        return hits

    @staticmethod
    def _normalize_published_date(value: str | None) -> str | None:
        """Keep only parseable ISO or RFC 2822 provider publication dates."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        with suppress(ValueError):
            return date.fromisoformat(cleaned).isoformat()
        iso_value = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
        with suppress(ValueError):
            return datetime.fromisoformat(iso_value).isoformat()
        with suppress(TypeError, ValueError, OverflowError):
            parsed = parsedate_to_datetime(cleaned)
            if parsed is not None:
                return parsed.isoformat()
        return None
