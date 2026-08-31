from sqlalchemy import text


async def test_extensions_enabled_after_upgrade(db_engine):
    async with db_engine.connect() as conn:
        rows = await conn.execute(text("SELECT extname FROM pg_extension"))
        names = {r[0] for r in rows}
    assert {"vector", "pg_trgm", "citext", "pgcrypto"}.issubset(names)


async def test_set_updated_at_function_exists(db_engine):
    async with db_engine.connect() as conn:
        row = await conn.execute(
            text("SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at'")
        )
        assert row.first() is not None
