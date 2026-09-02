from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.jobs.chunking import chunk_job
from app.domain.jobs.extractor import JDSkill, JobExtraction
from app.models.job import Job, JobChunk
from app.models.skill import Skill

_REQUIRED_WEIGHT = 0.8
_PREFERRED_WEIGHT = 0.4
# Columns that identify the seed row; never part of the ON CONFLICT update set.
_JOB_CONFLICT_SKIP = {"source_ref", "is_seed", "user_id"}


async def load_taxonomy() -> list[dict[str, Any]]:
    """Load and return the skill taxonomy from JSON file."""
    path = Path(__file__).parent / "domain" / "skills" / "taxonomy.json"
    return json.loads(path.read_text("utf-8"))


async def load_jobs_demo() -> list[dict[str, Any]]:
    """Load and return the hand-authored demo job dataset from JSON file."""
    path = Path(__file__).parent / "domain" / "jobs" / "jobs.demo.json"
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


def _compose_raw_text(
    row: dict[str, Any], responsibilities: list[str], requirement_labels: list[str]
) -> str:
    """Render a plain-text version of a demo row for ``jobs.raw_text``."""
    head = (
        f"{row['title']} at {row['company']}\n"
        f"{row.get('location') or ''} · {row.get('work_mode') or ''} · "
        f"{row.get('employment_type') or ''}\n\n"
        f"{row['description']}\n\n"
    )
    body = "Responsibilities:\n" + "\n".join(f"- {r}" for r in responsibilities)
    reqs = "\n\nRequirements:\n" + "\n".join(requirement_labels)
    return head + body + reqs


def _build_extraction(
    row: dict[str, Any],
    responsibilities: list[str],
    required_labels: list[str],
    preferred_labels: list[str],
) -> JobExtraction:
    return JobExtraction(
        title=row["title"],
        company=row["company"],
        company_domain=row.get("company_domain"),
        location=row.get("location"),
        work_mode=row.get("work_mode"),
        employment_type=row.get("employment_type"),
        seniority=row.get("seniority"),
        experience_min_years=row.get("experience_min_years"),
        experience_max_years=row.get("experience_max_years"),
        salary_min=row.get("salary_min"),
        salary_max=row.get("salary_max"),
        salary_currency=row.get("salary_currency"),
        salary_period=row.get("salary_period"),
        description=row["description"],
        responsibilities=responsibilities,
        required_skills=[JDSkill(raw=lbl, weight=_REQUIRED_WEIGHT) for lbl in required_labels],
        preferred_skills=[JDSkill(raw=lbl, weight=_PREFERRED_WEIGHT) for lbl in preferred_labels],
    )


async def seed_jobs(session: AsyncSession | None = None) -> int:
    """Seed the ``jobs`` table from the hand-authored demo dataset.

    Each row upserts a ``status="ready"`` seed ``Job`` keyed on its ``key``
    (stored as ``source_ref`` under the partial unique index
    ``uq_jobs_seed_source_ref``), resolves skill slugs against the ``skills``
    table, and replaces the job's ``job_chunks`` with freshly embedded chunks.
    Same ``session=None`` dual-path shape as :func:`seed_skills`.
    """
    entries = await load_jobs_demo()
    settings = get_settings()
    provider = get_embeddings_provider(settings)

    all_slugs: set[str] = set()
    for row in entries:
        all_slugs.update(row.get("required_skill_slugs", []))
        all_slugs.update(row.get("preferred_skill_slugs", []))

    async def _run(s: AsyncSession) -> None:
        resolved: dict[str, tuple[str, str]] = {}
        if all_slugs:
            rows = (
                await s.execute(
                    select(Skill.id, Skill.slug, Skill.label).where(Skill.slug.in_(all_slugs))
                )
            ).all()
            for r in rows:
                resolved[r.slug] = (str(r.id), r.label)

        for row in entries:
            req_slugs = [sl for sl in row.get("required_skill_slugs", []) if sl in resolved]
            pref_slugs = [sl for sl in row.get("preferred_skill_slugs", []) if sl in resolved]
            required_skills = [
                {
                    "skill_id": resolved[sl][0],
                    "slug": sl,
                    "label": resolved[sl][1],
                    "weight": _REQUIRED_WEIGHT,
                }
                for sl in req_slugs
            ]
            preferred_skills = [
                {
                    "skill_id": resolved[sl][0],
                    "slug": sl,
                    "label": resolved[sl][1],
                    "weight": _PREFERRED_WEIGHT,
                }
                for sl in pref_slugs
            ]
            req_labels = [resolved[sl][1] for sl in req_slugs]
            pref_labels = [resolved[sl][1] for sl in pref_slugs]
            responsibilities = list(row.get("responsibilities", []))

            extraction = _build_extraction(row, responsibilities, req_labels, pref_labels)
            posted_at = (
                dt.datetime.fromisoformat(row["posted_at"]).replace(tzinfo=dt.UTC)
                if row.get("posted_at")
                else None
            )

            payload: dict[str, Any] = {
                "source_ref": row["key"],
                "is_seed": True,
                "user_id": None,
                "source": "seed",
                "status": "ready",
                "raw_text": _compose_raw_text(row, responsibilities, req_labels + pref_labels),
                "title": row["title"],
                "company": row["company"],
                "company_domain": row.get("company_domain"),
                "location": row.get("location"),
                "work_mode": row.get("work_mode"),
                "employment_type": row.get("employment_type"),
                "seniority": row.get("seniority"),
                "experience_min_years": row.get("experience_min_years"),
                "experience_max_years": row.get("experience_max_years"),
                "salary_min": row.get("salary_min"),
                "salary_max": row.get("salary_max"),
                "salary_currency": row.get("salary_currency"),
                "salary_period": row.get("salary_period"),
                "salary_source": "estimate",
                "description": row["description"],
                "responsibilities": responsibilities,
                "required_skills": required_skills,
                "preferred_skills": preferred_skills,
                "structured": extraction.model_dump(),
                "extraction_meta": {
                    "seed": True,
                    "embed_model": provider.model,
                    "embed_dim": provider.dim,
                },
                "posted_at": posted_at,
            }
            update_set = {k: v for k, v in payload.items() if k not in _JOB_CONFLICT_SKIP}

            await s.execute(
                insert(Job)
                .values(**payload)
                .on_conflict_do_update(
                    index_elements=["source_ref"],
                    index_where=text("is_seed"),
                    set_=update_set,
                )
            )

            job_id = (
                await s.execute(
                    select(Job.id).where(Job.source_ref == row["key"], Job.is_seed.is_(True))
                )
            ).scalar_one()

            await s.execute(delete(JobChunk).where(JobChunk.job_id == job_id))

            drafts = chunk_job(extraction)
            if drafts:
                vectors = await provider.embed_documents([d.content for d in drafts])
                for draft, vec in zip(drafts, vectors, strict=True):
                    await s.execute(
                        insert(JobChunk).values(
                            job_id=job_id,
                            owner_id=None,
                            chunk_index=draft.chunk_index,
                            section=draft.section,
                            content=draft.content,
                            token_count=draft.token_count,
                            embed_model=provider.model,
                            embed_dim=provider.dim,
                            embedding=vec,
                        )
                    )

    if session is not None:
        await _run(session)
        await session.flush()
    else:
        async with AsyncSessionLocal() as s:
            await _run(s)
            await s.commit()

    return len(entries)


if __name__ == "__main__":
    target = sys.argv[1:2]
    if target == ["skills"]:
        n = asyncio.run(seed_skills())
        print(f"seeded {n} skills")
    elif target == ["jobs"]:
        n = asyncio.run(seed_jobs())
        print(f"seeded {n} jobs")
    elif target == ["all"]:

        async def _seed_all() -> tuple[int, int]:
            return await seed_skills(), await seed_jobs()

        skills_n, jobs_n = asyncio.run(_seed_all())
        print(f"seeded {skills_n} skills, {jobs_n} jobs")
    else:
        sys.exit("usage: python -m app.seed {skills|jobs|all}")
