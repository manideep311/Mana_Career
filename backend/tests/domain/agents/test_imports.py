def test_langgraph_core_imports_without_libpq():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    assert StateGraph is not None and MemorySaver is not None
    assert START != END


def test_search_provider_config_default(monkeypatch):
    from app.core.config import Settings

    # conftest pins SEARCH_PROVIDER=fake for agent tests; check the code default.
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    s = Settings(
        database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
        redis_url="redis://x", jwt_secret="x", _env_file=None,
    )
    # Web research is off unless a provider is configured explicitly.
    assert s.search_provider == "none" and s.search_api_key is None
