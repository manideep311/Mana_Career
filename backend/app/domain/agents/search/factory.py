from __future__ import annotations

from app.core.config import Settings
from app.domain.agents.search.adapters.disabled import DisabledSearchProvider
from app.domain.agents.search.adapters.fake import FakeSearchProvider
from app.domain.agents.search.adapters.tavily import TavilySearchProvider
from app.domain.agents.search.provider import SearchProvider


def get_search_provider(settings: Settings) -> SearchProvider:
    # Settings validation guarantees a key is present for tavily.
    if settings.search_provider == "tavily" and settings.search_api_key is not None:
        return TavilySearchProvider(settings.search_api_key.get_secret_value())
    if settings.search_provider == "fake":
        return FakeSearchProvider()
    return DisabledSearchProvider()
