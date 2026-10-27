"""Recompute every stored vector with the configured embeddings provider.

Needed after switching providers or models (fake -> local, local -> Voyage),
or after migration 0018 cleared vectors of the old size. First, any vector
column whose size differs from EMBED_DIM is resized (its HNSW index rebuilt);
then skills, learning resources, job chunks and résumé chunks are embedded
again in batches.

    python -m app.reembed          # or: just reembed
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.embeddings.provider import EmbeddingsProvider
from app.models import Base
from app.models.job import JobChunk
from app.models.learning import LearningResource
from app.models.resume_version import ResumeChunk
from app.models.skill import Skill
from app.seed import learning_embed_text, skill_embed_text

BATCH = 64


async def resize_vector_columns(conn: AsyncConnection, dim: int) -> list[str]:
    """Make every ``embedding`` column ``vector(dim)``; returns the tables changed.

    Existing vectors of another size can't be converted and are cleared.
    """
    resized: list[str] = []
    for table in Base.metadata.sorted_tables:
        column = table.c.get("embedding")
        if column is None or not isinstance(column.type, Vector):
            continue
        current = await conn.scalar(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = CAST(:t AS regclass) AND attname = 'embedding'"
            ),
            {"t": table.name},
        )
        if current == f"vector({dim})":
            continue
        indexes = [ix for ix in table.indexes if "embedding" in ix.columns]
        for ix in indexes:
            await conn.execute(text(f'DROP INDEX IF EXISTS "{ix.name}"'))
        await conn.execute(
            text(
                f'ALTER TABLE "{table.name}" ALTER COLUMN embedding '
                f"TYPE vector({dim}) USING NULL::vector({dim})"
            )
        )
        for ix in indexes:
            await conn.run_sync(ix.create)
        resized.append(table.name)
    if "resume_chunks" in resized:
        await conn.execute(
            text(f"ALTER TABLE resume_chunks ALTER COLUMN embed_dim SET DEFAULT {dim}")
        )
    return resized


async def _in_batches(
    session: AsyncSession,
    rows: Sequence[Any],
    texts: list[str],
    provider: EmbeddingsProvider,
    write: Any,
) -> int:
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        vectors = await provider.embed_documents(texts[start : start + BATCH])
        for row, vec in zip(chunk, vectors, strict=True):
            await session.execute(write(row, vec))
        await session.commit()
    return len(rows)


async def reembed_all(session: AsyncSession, provider: EmbeddingsProvider) -> dict[str, int]:
    """Re-embed every row that carries a vector; returns how many per table."""
    counts: dict[str, int] = {}

    skills = (await session.execute(select(Skill.id, Skill.label, Skill.aliases))).all()
    counts["skills"] = await _in_batches(
        session, skills, [skill_embed_text(r.label, list(r.aliases)) for r in skills], provider,
        lambda r, v: update(Skill).where(Skill.id == r.id).values(embedding=v),
    )

    resources = (
        await session.execute(
            select(
                LearningResource.id, LearningResource.title,
                LearningResource.summary, LearningResource.skills,
            )
        )
    ).all()
    counts["learning_resources"] = await _in_batches(
        session, resources,
        [learning_embed_text(r.title, r.summary, list(r.skills)) for r in resources], provider,
        lambda r, v: update(LearningResource)
        .where(LearningResource.id == r.id)
        .values(embedding=v),
    )

    for model, name in ((JobChunk, "job_chunks"), (ResumeChunk, "resume_chunks")):
        chunks = (await session.execute(select(model.id, model.content))).all()
        counts[name] = await _in_batches(
            session, chunks, [r.content for r in chunks], provider,
            lambda r, v, model=model: update(model)
            .where(model.id == r.id)
            .values(embedding=v, embed_model=provider.model, embed_dim=provider.dim),
        )
    return counts


async def main() -> None:
    settings = get_settings()
    provider = get_embeddings_provider(settings)
    async with AsyncSessionLocal() as session:
        conn = await session.connection()
        resized = await resize_vector_columns(conn, settings.embed_dim)
        await session.commit()
        if resized:
            print(f"resized to vector({settings.embed_dim}): {', '.join(resized)}")
        counts = await reembed_all(session, provider)
    summary = ", ".join(f"{n} {table}" for table, n in counts.items())
    print(f"re-embedded with {provider.model} ({provider.dim}-d): {summary}")


if __name__ == "__main__":
    asyncio.run(main())
