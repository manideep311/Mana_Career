"""Resizing the vector columns and re-embedding every stored row (app.reembed)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text, update

from app.domain.embeddings.adapters.fake import FakeEmbeddingsProvider
from app.models.job import JobChunk
from app.models.learning import LearningResource
from app.models.skill import Skill
from app.models.vector import EMBED_DIM
from app.reembed import reembed_all, resize_vector_columns
from app.seed import seed_jobs, seed_learning_resources, seed_skills, skill_embed_text

VECTOR_TABLES = {"skills", "job_chunks", "resume_chunks", "learning_resources"}


async def _column_type(session, table: str) -> str:
    return (
        await session.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = CAST(:t AS regclass) AND attname = 'embedding'"
            ),
            {"t": table},
        )
    ).scalar_one()


async def test_resize_changes_every_vector_column_and_rebuilds_its_index(db_session):
    conn = await db_session.connection()
    assert await resize_vector_columns(conn, EMBED_DIM) == []  # already the right size

    assert set(await resize_vector_columns(conn, 8)) == VECTOR_TABLES
    for table in VECTOR_TABLES:
        assert await _column_type(db_session, table) == "vector(8)"
    indexes = (
        await db_session.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE indexname LIKE '%embedding'")
        )
    ).all()
    assert {name for name, _ in indexes} >= {f"ix_{t}_embedding" for t in VECTOR_TABLES}
    assert all("hnsw" in d and "vector_cosine_ops" in d for _, d in indexes)
    default = (
        await db_session.execute(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'resume_chunks' AND column_name = 'embed_dim'"
            )
        )
    ).scalar_one()
    assert default == "8"
    # (The fixture rolls the transaction back, DDL included.)


async def test_reembed_fills_every_vector_with_the_new_provider(db_session):
    await seed_skills(db_session)
    await seed_learning_resources(db_session)
    await seed_jobs(db_session)
    for model in (Skill, LearningResource, JobChunk):
        await db_session.execute(update(model).values(embedding=None))

    provider = FakeEmbeddingsProvider(EMBED_DIM, "fake-embed-2")
    counts = await reembed_all(db_session, provider)

    assert counts["skills"] > 0 and counts["learning_resources"] > 0
    assert counts["job_chunks"] > 0
    for model in (Skill, LearningResource, JobChunk):
        missing = await db_session.scalar(
            select(func.count()).select_from(model).where(model.embedding.is_(None))
        )
        assert missing == 0
    skill = (await db_session.execute(select(Skill).limit(1))).scalar_one()
    expected = await provider.embed_documents([skill_embed_text(skill.label, skill.aliases)])
    # pgvector stores float32.
    assert list(skill.embedding) == pytest.approx(expected[0], abs=1e-6)
    models = (await db_session.execute(select(JobChunk.embed_model).distinct())).scalars().all()
    assert models == ["fake-embed-2"]
