from __future__ import annotations

from app.core.config import Settings
from app.domain.agents.search.adapters.fake import FakeSearchProvider
from app.domain.agents.search.adapters.tavily import TavilySearchProvider
from app.domain.agents.search.provider import SearchProvider


def get_search_provider(settings: Settings) -> SearchProvider:
    if settings.search_provider == "fake":
        return FakeSearchProvider()
    if settings.search_provider == "tavily" and settings.search_api_key:
        return TavilySearchProvider(settings.search_api_key.get_secret_value())
    raise ValueError("A supported search provider and its credentials are required")
