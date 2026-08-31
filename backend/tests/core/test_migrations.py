from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import make_engine


async def test_extensions_enabled_after_upgrade(db_engine):
    eng = make_engine(get_settings().database_url)
    async with eng.connect() as conn:
        rows = await conn.execute(text("SELECT extname FROM pg_extension"))
        names = {r[0] for r in rows}
    await eng.dispose()
    assert {"vector", "pg_trgm", "citext", "pgcrypto"}.issubset(names)


async def test_set_updated_at_function_exists(db_engine):
    eng = make_engine(get_settings().database_url)
    async with eng.connect() as conn:
        row = await conn.execute(
            text("SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at'")
        )
        assert row.first() is not None
    await eng.dispose()
