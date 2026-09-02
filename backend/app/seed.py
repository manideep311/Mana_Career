from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.domain.embeddings.factory import get_embeddings_provider
from app.models.skill import Skill


async def load_taxonomy() -> list[dict[str, Any]]:
    """Load and return the skill taxonomy from JSON file."""
    path = Path(__file__).parent / "domain" / "skills" / "taxonomy.json"
    return json.loads(path.read_text("utf-8"))


async def seed_skills(session: AsyncSession | None = None) -> int:
    """Seed the skills table with taxonomy entries and embeddings.

    With no ``session`` this opens its own ``AsyncSessionLocal`` and commits
    (the CLI / one-shot path). Pass a ``session`` (e.g. from a test's
    rolled-back transaction) to run inside a caller-owned unit of work — the
    rows are ``flush``ed, not committed.
    """
    entries = await load_taxonomy()
    settings = get_settings()
    provider = get_embeddings_provider(settings)

    async def _run(s: AsyncSession) -> None:
        for entry in entries:
            slug = entry["slug"]
            label = entry["label"]
            category = entry["category"]
            aliases = entry["aliases"]

            # Create text for embedding
            text = f"{label}: {', '.join(aliases)}" if aliases else label

            # Generate embedding
            vec = await provider.embed_query(text)

            # Upsert with conflict resolution
            stmt = (
                insert(Skill)
                .values(
                    slug=slug,
                    label=label,
                    category=category,
                    aliases=aliases,
                    embedding=vec,
                )
                .on_conflict_do_update(
                    index_elements=["slug"],
                    set_={
                        "label": label,
                        "category": category,
                        "aliases": aliases,
                        "embedding": vec,
                    },
                )
            )

            await s.execute(stmt)

    if session is not None:
        await _run(session)
        await session.flush()
    else:
        async with AsyncSessionLocal() as s:
            await _run(s)
            await s.commit()

    return len(entries)


if __name__ == "__main__":
    if sys.argv[1:2] == ["skills"]:
        n = asyncio.run(seed_skills())
        print(f"seeded {n} skills")
    else:
        sys.exit("usage: python -m app.seed skills")
