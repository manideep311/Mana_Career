from __future__ import annotations

from typing import Protocol, TypedDict


class SearchHit(TypedDict):
    url: str
    title: str
    content: str


class SearchProvider(Protocol):
    async def search(self, query: str, *, k: int = 5) -> list[SearchHit]: ...
