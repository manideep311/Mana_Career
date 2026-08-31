from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

os.environ.setdefault("ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("DATABASE_URL_TEST", "postgresql+asyncpg://mana:mana@localhost:5432/mana_test"),
)
os.environ.setdefault("DATABASE_URL_TEST", os.environ["DATABASE_URL"])
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("REFRESH_COOKIE_SECURE", "false")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "fake")
os.environ.setdefault("EMBED_DIM", "1024")


@pytest.fixture(scope="session")
def _migrated() -> None:
    """Bring the test database to head once per session.

    Runs Alembic in a subprocess so its own ``asyncio.run`` in env.py does not
    nest inside pytest-asyncio's running loop.
    """
    backend_dir = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        check=True,
    )


@pytest.fixture(scope="session")
async def db_engine(_migrated: None) -> AsyncIterator[object]:
    from app.core.config import get_settings
    from app.core.db import make_engine

    eng = make_engine(get_settings().database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(db_engine: object) -> AsyncIterator[object]:
    from sqlalchemy.ext.asyncio import AsyncSession

    conn = await db_engine.connect()  # type: ignore[attr-defined]
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


@pytest.fixture
async def client(db_session: object) -> AsyncIterator[object]:
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from app.core.db import get_session
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


@pytest.fixture
def fake_redis() -> object:
    class _FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, int] = {}

        async def incr(self, key: str) -> int:
            self.store[key] = self.store.get(key, 0) + 1
            return self.store[key]

        async def expire(self, key: str, ttl: int) -> None:
            return None

        async def ttl(self, key: str) -> int:
            return 42

        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    return _FakeRedis()
