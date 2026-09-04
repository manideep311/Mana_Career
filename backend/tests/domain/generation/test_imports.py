def test_new_packages_import():
    import app.domain.documents
    import app.domain.generation  # noqa: F401


def test_doc_render_flag_defaults_true():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
        redis_url="redis://x", jwt_secret="x",
    )
    assert s.doc_render_enabled is True
