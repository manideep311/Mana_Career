from __future__ import annotations

from typing import NotRequired, Protocol, TypedDict


class SearchHit(TypedDict):
    url: str
    title: str
    content: str
    published_date: NotRequired[str | None]
    retrieved_at: NotRequired[str]


class SearchProviderError(RuntimeError):
    """A safe, non-sensitive error from a search provider."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SearchNotConfiguredError(SearchProviderError):
    """Web research is switched off (``SEARCH_PROVIDER=none``)."""


class SearchProvider(Protocol):
    async def search(self, query: str, *, k: int = 5) -> list[SearchHit]: ...
