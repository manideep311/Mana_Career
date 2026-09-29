from __future__ import annotations

from app.domain.agents.search.provider import SearchHit, SearchNotConfiguredError


class DisabledSearchProvider:
    """Used when ``SEARCH_PROVIDER=none``: research is reported as skipped."""

    async def search(self, query: str, *, k: int = 5) -> list[SearchHit]:
        raise SearchNotConfiguredError("Web research isn't configured")
