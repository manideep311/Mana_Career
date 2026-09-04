from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from app.core.config import Settings

_saver: Any | None = None
_cm: Any | None = None


def _psycopg_dsn(settings: Settings) -> str:
    """Return the psycopg-style DSN by stripping the asyncpg driver token."""
    return settings.database_url.replace("+asyncpg", "")


async def get_checkpointer(settings: Settings) -> Any:
    """Return the process-singleton LangGraph checkpointer.

    In ``test`` env this is an in-memory :class:`MemorySaver`. Otherwise an
    ``AsyncPostgresSaver`` is lazily constructed (its import is deferred so the
    module loads on boxes without libpq) and its async context manager is kept
    alive in a module global so it is never garbage-collected.
    """
    global _saver, _cm

    if _saver is not None:
        return _saver

    if settings.env == "test":
        _saver = MemorySaver()
        return _saver

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    _cm = AsyncPostgresSaver.from_conn_string(_psycopg_dsn(settings))
    _saver = await _cm.__aenter__()
    return _saver


async def ensure_checkpointer_tables(settings: Settings) -> None:
    """Create the checkpointer tables. A no-op in ``test`` env."""
    if settings.env == "test":
        return
    saver = await get_checkpointer(settings)
    await saver.setup()


def _reset_for_tests() -> None:
    """Drop the cached singleton. Used by a test fixture; not called in prod."""
    global _saver, _cm
    _saver = None
    _cm = None
