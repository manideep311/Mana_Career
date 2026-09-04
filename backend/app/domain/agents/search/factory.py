from __future__ import annotations

from app.core.config import Settings
from app.domain.agents.search.adapters.fake import FakeSearchProvider
from app.domain.agents.search.provider import SearchProvider


def get_search_provider(settings: Settings) -> SearchProvider:
    if settings.search_provider == "fake":
        return FakeSearchProvider()
    raise NotImplementedError(
        f"{settings.search_provider!r} search adapter lands in a later phase"
    )
