from __future__ import annotations

import itertools
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

# Each `client` fixture instance gets its own source IP so the per-IP auth
# rate-limit bucket (10/min) does not carry across tests when Redis is real (CI).
_client_ip_seq = itertools.count(1)


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
    n = next(_client_ip_seq)
    ip = f"10.{n >> 16 & 255}.{n >> 8 & 255}.{n & 255}"
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, client=(ip, 12345)),
            base_url="http://test",
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

        async def publish(self, channel: str, message: str) -> int:
            return 0

        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    return _FakeRedis()


@pytest.fixture(autouse=True)
def _no_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop résumé uploads from reaching the real ARQ Redis pool.

    Tests that assert on ``enqueue`` re-patch it in their own body (this fixture
    runs first, so their patch wins).
    """

    async def _noop(*args: object, **kwargs: object) -> str:
        return "test-job"

    monkeypatch.setattr("app.domain.resume.service.enqueue", _noop, raising=False)


@pytest.fixture(autouse=True)
def _tmp_file_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep résumé uploads out of the repo working tree.

    ``ResumeService`` calls ``get_file_store(settings)`` when no ``file_store`` is
    passed; the default ``LocalFileStore`` root is ``./var/files`` (inside the
    repo). Redirect it to a pytest ``tmp_path`` dir. Tests that pass their own
    ``file_store=`` (Task 8's ``_svc``) never hit this path.
    """
    from app.infra.storage.local import LocalFileStore

    store = LocalFileStore(str(tmp_path / "files"))
    monkeypatch.setattr(
        "app.domain.resume.service.get_file_store",
        lambda _settings: store,
        raising=False,
    )
