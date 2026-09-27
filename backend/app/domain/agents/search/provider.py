from __future__ import annotations

from typing import NotRequired, Protocol, TypedDict


class SearchHit(TypedDict):
    url: str
    title: str
    content: str
    published_date: NotRequired[str | None]
    retrieved_at: NotRequired[str]


class SearchProvider(Protocol):
    async def search(self, query: str, *, k: int = 5) -> list[SearchHit]: ...
