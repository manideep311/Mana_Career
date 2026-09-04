import pytest

from app.domain.agents.search.adapters.fake import FakeSearchProvider
from app.domain.agents.search.factory import get_search_provider


async def test_fake_search_is_deterministic_and_bounded():
    p = FakeSearchProvider()
    a = await p.search("acme robotics perception", k=2)
    b = await p.search("acme robotics perception", k=2)
    assert a == b and len(a) == 2
    assert all({"url", "title", "content"} <= set(h) for h in a)


async def test_fake_search_varies_by_query():
    p = FakeSearchProvider()
    assert await p.search("alpha", k=3) != await p.search("omega", k=3)


def test_factory_fake_and_notimplemented(monkeypatch):
    from app.core.config import Settings

    base = dict(database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
                redis_url="redis://x", jwt_secret="x")
    assert isinstance(get_search_provider(Settings(**base)), FakeSearchProvider)
    with pytest.raises(NotImplementedError):
        get_search_provider(Settings(**base, search_provider="tavily"))
