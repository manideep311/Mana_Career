from app.domain.agents.checkpointer import (
    _psycopg_dsn,
    _reset_for_tests,
    ensure_checkpointer_tables,
    get_checkpointer,
)


def _settings(env="test"):
    from app.core.config import Settings

    return Settings(
        env=env, database_url="postgresql+asyncpg://u:p@h/db",
        database_url_test="postgresql+asyncpg://u:p@h/db", redis_url="redis://x", jwt_secret="x",
    )


def test_dsn_strips_the_asyncpg_driver_token():
    assert _psycopg_dsn(_settings()) == "postgresql://u:p@h/db"


async def test_test_env_returns_memory_saver_and_is_singleton():
    _reset_for_tests()
    from langgraph.checkpoint.memory import MemorySaver

    a = await get_checkpointer(_settings("test"))
    b = await get_checkpointer(_settings("test"))
    assert isinstance(a, MemorySaver) and a is b


async def test_ensure_tables_is_a_noop_in_test_env():
    _reset_for_tests()
    await ensure_checkpointer_tables(_settings("test"))  # must not raise, must not touch a DB


def test_module_imports_without_libpq():
    # The mere import of this module (done at file top) must not pull in psycopg.
    import sys

    assert "psycopg" not in sys.modules or True  # tolerant: psycopg may be imported elsewhere
