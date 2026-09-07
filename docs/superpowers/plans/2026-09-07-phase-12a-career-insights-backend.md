# Phase 12a — Career insights (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The forward-looking guidance backend — aggregate skill gaps, a seeded learning catalog, a `RoadmapPlanner` that streams milestones grounded in real catalog entries, and the `/roadmaps` + `/learning-resources` + `/insights` APIs.

**Architecture:** New `learning_resources` / `learning_recommendations` / `roadmap_milestones` tables (migration `0015`). New `app/domain/roadmap/` (planner + service) and `app/domain/insights/` (ranker + composer) packages. New `app/worker/tasks/roadmap.py`. New routers `roadmaps.py` + `insights.py`; additions to `skill_gaps.py`. Streamed milestones use a dedicated `sse:roadmap:{id}` Redis channel relayed by `GET /roadmaps/{id}/events`, mirroring `/jobs/{id}/events`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, ARQ + Redis, pgvector, `sse-starlette`.

**Spec:** `docs/superpowers/specs/2026-09-07-phase-12a-career-insights-backend.md` — read first (8 rulings R1–R8).

## Global Constraints

- Backend-only. Phase 12b is the Insights page + roadmap timeline UI.
- `$UV` = `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`. If `"$UV" run` fails with a missing interpreter: `"$UV" venv --python 3.12 && "$UV" sync` in `backend/` (rebuilds from the intact `uv.lock` — never edit `uv.lock`).
- No local Postgres/Redis. Local gate (all clean), from `backend/`: `"$UV" run ruff check .` / `"$UV" run mypy app` / `"$UV" run lint-imports` (stays **`3 kept, 0 broken`**) / `"$UV" run pytest -q --collect-only` (0 errors) + any pure suite added. DB-gated tests run in CI only (they ERROR locally at `tests/conftest.py`'s `_migrated`).
- Alembic chain: `…→0014_application_events→0015_learning_roadmap`, single head. Mirror `0013_applications_approvals.py`'s style (`_TS`/`_NOW` locals, `pg.UUID`/`pg.JSONB`, inline `sa.CheckConstraint`, `op.execute("CREATE TRIGGER trg_<t>_set_updated_at BEFORE UPDATE ON <t> FOR EACH ROW EXECUTE FUNCTION set_updated_at()")` for every `TimestampMixin` table; `set_updated_at()` is defined in `0001_bootstrap`).
- `mypy --strict`. Every def fully annotated. `Command`-style generics need explicit params.
- Domain packages are **leaves**: `app.domain.roadmap` and `app.domain.insights` may import `app.core.*`, `app.models.*`, and (roadmap only) `app.domain.llm.*` / `app.domain.embeddings.*` — never `app.api.*`, `app.worker.*`, or a sibling business domain (`matching`, `jobs`, `rag`, …). `lint-imports` stays `3 kept, 0 broken` (the layered contract treats all of `app.domain` as one layer, so `roadmap → llm`/`embeddings` is allowed; `roadmap`/`insights` must NOT import `app.domain.rag`).
- `pgvector` dim is the literal `Vector(1024)` everywhere (matches `app/models/skill.py` / `app/models/job.py` and `Settings.embed_dim` default 1024), with the "keep in sync" comment.
- `git commit -m` messages: plain text, NO backticks.

---

## Task 1: migration `0015` + 3 models — SUBAGENT REVIEW

**Files:** Create `backend/app/models/learning.py`, `backend/alembic/versions/0015_learning_roadmap.py`, `backend/tests/models/test_learning_models.py`. Modify `backend/app/models/__init__.py`.

**Interfaces:**
- Produces: `LearningResource`, `LearningRecommendation`, `RoadmapMilestone` (tables `learning_resources` / `learning_recommendations` / `roadmap_milestones`); single alembic head `0015_learning_roadmap`.

- [ ] **Step 1: `app/models/learning.py`**
```python
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LearningResource(Base, TimestampMixin):
    __tablename__ = "learning_resources"
    __table_args__ = (
        CheckConstraint(
            "type in ('course','book','doc','video','article','project')",
            name="learning_resources_type_valid",
        ),
        CheckConstraint(
            "level in ('beginner','intermediate','advanced')",
            name="learning_resources_level_valid",
        ),
        CheckConstraint(
            "cost in ('free','paid','freemium')", name="learning_resources_cost_valid"
        ),
        Index(
            "ix_learning_resources_embedding", "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_learning_resources_skills", "skills", postgresql_using="gin"),
        Index("ix_learning_resources_level", "level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(12), nullable=False)
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    est_hours: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[str] = mapped_column(String(10), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # The literal dim must stay in sync with app/core/config.py `embed_dim`
    # (default 1024) and the migration's Vector(1024).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    is_active: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("true")
    )


class LearningRecommendation(Base, TimestampMixin):
    __tablename__ = "learning_recommendations"
    __table_args__ = (
        CheckConstraint(
            "scope in ('aggregate','job')", name="learning_recommendations_scope_valid"
        ),
        CheckConstraint(
            "status in ('planning','active','archived')",
            name="learning_recommendations_status_valid",
        ),
        Index("ix_learning_recommendations_user", "user_id", text("created_at DESC")),
        Index("ix_learning_recommendations_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(12), nullable=False)
    # No FK: `jobs` rows can be seed rows the user doesn't own; loose reference.
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    summary: Mapped[str | None] = mapped_column(Text)
    next_step: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'planning'")
    )
    generation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class RoadmapMilestone(Base, TimestampMixin):
    __tablename__ = "roadmap_milestones"
    __table_args__ = (
        CheckConstraint(
            "status in ('not_started','in_progress','done')",
            name="roadmap_milestones_status_valid",
        ),
        Index("ix_roadmap_milestones_rec", "recommendation_id", "order_index"),
        Index("ix_roadmap_milestones_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # No FK: skills come from the taxonomy; loose reference.
    skill_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    skill_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_label: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    resource_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'")
    )
    est_hours: Mapped[int | None] = mapped_column(Integer)
    practice_project: Mapped[str | None] = mapped_column(Text)
    checkpoint: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'not_started'")
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column()
```

- [ ] **Step 2: `app/models/__init__.py`** — insert alphabetically. `learning` sorts after `job` and before `match`:
```python
from app.models import job as job
from app.models import learning as learning
from app.models import match as match
```

- [ ] **Step 3: `alembic/versions/0015_learning_roadmap.py`**
```python
"""learning_resources + learning_recommendations + roadmap_milestones

Revision ID: 0015_learning_roadmap
Revises: 0014_application_events
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0015_learning_roadmap"
down_revision = "0014_application_events"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def _updated_at_trigger(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def upgrade() -> None:
    op.create_table(
        "learning_resources",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("url", sa.String(500), nullable=False, unique=True),
        sa.Column("type", sa.String(12), nullable=False),
        sa.Column("skills", sa.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("est_hours", sa.Integer),
        sa.Column("cost", sa.String(10), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("type in ('course','book','doc','video','article','project')",
                           name="learning_resources_type_valid"),
        sa.CheckConstraint("level in ('beginner','intermediate','advanced')",
                           name="learning_resources_level_valid"),
        sa.CheckConstraint("cost in ('free','paid','freemium')",
                           name="learning_resources_cost_valid"),
    )
    op.create_index("ix_learning_resources_embedding", "learning_resources", ["embedding"],
                    postgresql_using="hnsw",
                    postgresql_ops={"embedding": "vector_cosine_ops"})
    op.create_index("ix_learning_resources_skills", "learning_resources", ["skills"],
                    postgresql_using="gin")
    op.create_index("ix_learning_resources_level", "learning_resources", ["level"])
    _updated_at_trigger("learning_resources")

    op.create_table(
        "learning_recommendations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("constraints", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", sa.Text),
        sa.Column("next_step", sa.Text),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'planning'")),
        sa.Column("generation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("scope in ('aggregate','job')",
                           name="learning_recommendations_scope_valid"),
        sa.CheckConstraint("status in ('planning','active','archived')",
                           name="learning_recommendations_status_valid"),
    )
    op.create_index("ix_learning_recommendations_user", "learning_recommendations",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_learning_recommendations_user_status", "learning_recommendations",
                    ["user_id", "status"])
    _updated_at_trigger("learning_recommendations")

    op.create_table(
        "roadmap_milestones",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("recommendation_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("learning_recommendations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("skill_id", pg.UUID(as_uuid=True)),
        sa.Column("skill_slug", sa.String(120), nullable=False),
        sa.Column("skill_label", sa.String(160), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("why_it_matters", sa.Text, nullable=False),
        sa.Column("resource_ids", sa.ARRAY(pg.UUID(as_uuid=True)), nullable=False,
                  server_default=sa.text("'{}'")),
        sa.Column("est_hours", sa.Integer),
        sa.Column("practice_project", sa.Text),
        sa.Column("checkpoint", sa.Text),
        sa.Column("status", sa.String(12), nullable=False,
                  server_default=sa.text("'not_started'")),
        sa.Column("completed_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("status in ('not_started','in_progress','done')",
                           name="roadmap_milestones_status_valid"),
    )
    op.create_index("ix_roadmap_milestones_rec", "roadmap_milestones",
                    ["recommendation_id", "order_index"])
    op.create_index("ix_roadmap_milestones_user", "roadmap_milestones", ["user_id"])
    _updated_at_trigger("roadmap_milestones")


def downgrade() -> None:
    for t in ("roadmap_milestones", "learning_recommendations", "learning_resources"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_set_updated_at ON {t}")
        op.drop_table(t)
```

- [ ] **Step 4: `tests/models/test_learning_models.py`** (DB-gated)
```python
"""learning_* model round-trips -- DB integration, CI-deferred."""
from __future__ import annotations

from app.models.learning import (
    LearningRecommendation,
    LearningResource,
    RoadmapMilestone,
)
from app.models.user import User


async def test_learning_models_round_trip(db_session):
    u = User(email="learn@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()

    res = LearningResource(
        title="SQL Performance Explained", provider="Markus Winand", url="https://use-the-index-luke.com",
        type="book", skills=["sql", "databases"], level="intermediate", cost="free",
        summary="Indexing and query tuning from first principles.",
    )
    db_session.add(res)
    await db_session.flush()
    await db_session.refresh(res)
    assert res.is_active is True and res.skills == ["sql", "databases"]

    rec = LearningRecommendation(user_id=u.id, scope="aggregate", title="Learning roadmap")
    db_session.add(rec)
    await db_session.flush()
    await db_session.refresh(rec)
    assert rec.status == "planning" and rec.constraints == {}

    ms = RoadmapMilestone(
        recommendation_id=rec.id, user_id=u.id, order_index=0,
        skill_slug="sql", skill_label="SQL", title="Master indexing",
        why_it_matters="Every backend role expects it.", resource_ids=[res.id],
    )
    db_session.add(ms)
    await db_session.flush()
    await db_session.refresh(ms)
    assert ms.status == "not_started" and ms.resource_ids == [res.id]
```

- [ ] **Step 5: gate**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run alembic heads`
Expected: `lint-imports` `3 kept, 0 broken`; collection error-free; `alembic heads` → `0015_learning_roadmap (head)`.

```bash
git add backend/app/models/learning.py backend/app/models/__init__.py backend/alembic/versions/0015_learning_roadmap.py backend/tests/models/test_learning_models.py
git commit -m "feat(insights): learning_resources + learning_recommendations + roadmap_milestones (migration 0015)"
```

---

## Task 2: learning-resource catalog + `seed_learning_resources()`

**Files:** Create `backend/app/domain/roadmap/__init__.py`, `backend/app/domain/roadmap/learning_resources.json`. Modify `backend/app/seed.py`, `backend/tests/domain/skills/test_seed.py` (or a new `tests/domain/roadmap/test_seed.py`).

**Interfaces:**
- Consumes: `LearningResource` (Task 1), `get_embeddings_provider`.
- Produces: `seed_learning_resources(session: AsyncSession | None = None) -> int`; `python -m app.seed learning` and `python -m app.seed all` both load it.

- [ ] **Step 1: `app/domain/roadmap/__init__.py`** — empty.

- [ ] **Step 2: `app/domain/roadmap/learning_resources.json`** — a hand-authored array of **~50** objects. Each: `{"title", "provider", "url", "type", "skills": [<taxonomy slugs>], "level", "est_hours", "cost", "summary"}`. `url` must be unique. Cover the highest-value skills in `app/domain/skills/taxonomy.json` — read that file first and use real slugs. Spread across `type` (`course`/`book`/`doc`/`video`/`article`/`project`), `level`, `cost`. Example entries (write ~50 in this shape, real URLs, 1–2 sentence summaries):
```json
[
  {
    "title": "The Rust Programming Language (\"the book\")",
    "provider": "rust-lang.org",
    "url": "https://doc.rust-lang.org/book/",
    "type": "doc",
    "skills": ["rust"],
    "level": "beginner",
    "est_hours": 30,
    "cost": "free",
    "summary": "The official, comprehensive introduction to Rust: ownership, traits, error handling, and concurrency."
  },
  {
    "title": "Designing Data-Intensive Applications",
    "provider": "Martin Kleppmann",
    "url": "https://dataintensive.net/",
    "type": "book",
    "skills": ["distributed-systems", "databases", "system-design"],
    "level": "advanced",
    "est_hours": 40,
    "cost": "paid",
    "summary": "The reference on replication, partitioning, consistency, and the trade-offs behind modern data systems."
  },
  {
    "title": "Build a small in-memory key-value store",
    "provider": "self-directed",
    "url": "https://github.com/topics/key-value-store",
    "type": "project",
    "skills": ["data-structures", "concurrency", "system-design"],
    "level": "intermediate",
    "est_hours": 12,
    "cost": "free",
    "summary": "Implement GET/SET/DEL with TTL and an LRU eviction policy; add a write-ahead log and a background compactor."
  }
]
```
**NOTE for the implementer:** if a skill you want a resource for has no taxonomy slug, either pick the closest existing slug or add the resource against a broader slug — do NOT invent slugs. It is fine for a resource to list 1–3 slugs.

- [ ] **Step 3: `app/seed.py`** — add after `seed_jobs`:
```python
async def load_learning_resources() -> list[dict[str, Any]]:
    path = Path(__file__).parent / "domain" / "roadmap" / "learning_resources.json"
    return json.loads(path.read_text("utf-8"))


async def seed_learning_resources(session: AsyncSession | None = None) -> int:
    """Seed ``learning_resources`` from the hand-authored catalog.

    Upserts on ``url``; embeds ``"{title}. {summary} Skills: {slugs}"``. Same
    ``session=None`` dual-path shape as :func:`seed_skills`.
    """
    from app.models.learning import LearningResource

    entries = await load_learning_resources()
    settings = get_settings()
    provider = get_embeddings_provider(settings)

    async def _run(s: AsyncSession) -> None:
        for e in entries:
            skills = list(e.get("skills", []))
            embed_text = f"{e['title']}. {e['summary']} Skills: {', '.join(skills)}"
            vec = await provider.embed_query(embed_text)
            stmt = (
                insert(LearningResource)
                .values(
                    title=e["title"], provider=e["provider"], url=e["url"], type=e["type"],
                    skills=skills, level=e["level"], est_hours=e.get("est_hours"),
                    cost=e["cost"], summary=e["summary"], embedding=vec, is_active=True,
                )
                .on_conflict_do_update(
                    index_elements=["url"],
                    set_={
                        "title": e["title"], "provider": e["provider"], "type": e["type"],
                        "skills": skills, "level": e["level"], "est_hours": e.get("est_hours"),
                        "cost": e["cost"], "summary": e["summary"], "embedding": vec,
                        "is_active": True,
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
```
Wire the `__main__` block: add an `elif target == ["learning"]:` branch (`n = asyncio.run(seed_learning_resources()); print(f"seeded {n} learning resources")`), extend `_seed_all` to also call `seed_learning_resources()` and its print, and update the `usage:` string to `{skills|jobs|learning|all}`.

- [ ] **Step 4: `tests/domain/roadmap/__init__.py`** (empty) + `tests/domain/roadmap/test_seed.py`** (DB-gated)
```python
"""learning-resource seed -- DB integration, CI-deferred."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models.learning import LearningResource
from app.seed import seed_learning_resources


async def test_seed_learning_resources_is_idempotent(db_session):
    n1 = await seed_learning_resources(db_session)
    assert n1 >= 40
    count1 = (await db_session.execute(select(func.count()).select_from(LearningResource))).scalar_one()
    n2 = await seed_learning_resources(db_session)
    count2 = (await db_session.execute(select(func.count()).select_from(LearningResource))).scalar_one()
    assert count1 == count2 == n1 == n2
    row = (await db_session.execute(select(LearningResource).limit(1))).scalar_one()
    assert row.embedding is not None and len(row.embedding) == 1024
```
Also add a **pure** guard test `tests/domain/roadmap/test_catalog_json.py` (runs locally — no DB):
```python
"""The learning-resource catalog JSON is well-formed."""
from __future__ import annotations

import json
from pathlib import Path

_VALID_TYPE = {"course", "book", "doc", "video", "article", "project"}
_VALID_LEVEL = {"beginner", "intermediate", "advanced"}
_VALID_COST = {"free", "paid", "freemium"}


def test_catalog_entries_are_valid():
    path = Path("app/domain/roadmap/learning_resources.json")
    entries = json.loads(path.read_text("utf-8"))
    assert len(entries) >= 40
    urls = [e["url"] for e in entries]
    assert len(urls) == len(set(urls)), "duplicate url in catalog"
    for e in entries:
        assert e["type"] in _VALID_TYPE
        assert e["level"] in _VALID_LEVEL
        assert e["cost"] in _VALID_COST
        assert isinstance(e["skills"], list) and e["skills"]
        assert e["summary"] and e["title"] and e["provider"]
```

- [ ] **Step 5: gate + run the pure test**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/roadmap/test_catalog_json.py`
Expected: all clean; the catalog test passes.

```bash
git add backend/app/domain/roadmap backend/app/seed.py backend/tests/domain/roadmap
git commit -m "feat(insights): learning-resource catalog + seed_learning_resources()"
```

---

## Task 3: skill-gap aggregate

**Files:** Modify `backend/app/domain/matching/service.py`, `backend/app/api/v1/skill_gaps.py`. Create `backend/tests/domain/matching/test_aggregate_gaps.py` (DB-gated).

**Interfaces:**
- Consumes: `SkillGap`, `JobMatch`, `_severity_rank` (existing module-level `case()` in `matching/service.py`).
- Produces: `MatchService.aggregate_skill_gaps(user_id) -> list[SkillGap]`; `POST /skill-gaps/aggregate -> list[SkillGapOut]` (200).

- [ ] **Step 1: `matching/service.py`** — add a method (place near `list_skill_gaps`). Read the file's existing imports first; it already imports `select`, `delete`, `func`, `SkillGap`, `JobMatch`, `_severity_rank`.
```python
    _SEV_ORDER = {"critical": 0, "important": 1, "nice_to_have": 2}

    async def aggregate_skill_gaps(self, user_id: uuid.UUID) -> list[SkillGap]:
        """Roll every job-scoped gap into one `scope='aggregate'` row per skill.

        Deterministic, no LLM. Delete-then-insert so re-running is idempotent.
        """
        await self.session.execute(
            delete(SkillGap).where(
                SkillGap.user_id == user_id, SkillGap.scope == "aggregate"
            )
        )
        rows = (
            await self.session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == user_id, SkillGap.scope == "job"
                )
            )
        ).scalars().all()

        by_skill: dict[uuid.UUID, dict[str, object]] = {}
        for g in rows:
            acc = by_skill.setdefault(
                g.skill_id,
                {
                    "skill_slug": g.skill_slug, "skill_label": g.skill_label,
                    "severity": g.severity, "matches": set(),
                },
            )
            if self._SEV_ORDER[g.severity] < self._SEV_ORDER[str(acc["severity"])]:
                acc["severity"] = g.severity
            if g.job_match_id is not None:
                cast("set[uuid.UUID]", acc["matches"]).add(g.job_match_id)

        made: list[SkillGap] = []
        for skill_id, acc in by_skill.items():
            freq = max(1, len(cast("set[uuid.UUID]", acc["matches"])))
            row = SkillGap(
                user_id=user_id, scope="aggregate", job_match_id=None, skill_id=skill_id,
                skill_slug=str(acc["skill_slug"]), skill_label=str(acc["skill_label"]),
                severity=str(acc["severity"]), frequency=freq,
                rationale=f"Missing in {freq} of your job matches.", status="open",
            )
            self.session.add(row)
            made.append(row)
        await self.session.flush()
        return made
```
Add `from typing import cast` to the file's imports if absent. Also update `list_skill_gaps`'s `order_by`: when `scope == "aggregate"`, order by `_severity_rank, SkillGap.frequency.desc()`; else keep `_severity_rank, SkillGap.skill_label`.

- [ ] **Step 2: `app/api/v1/skill_gaps.py`** — add the route:
```python
from fastapi import APIRouter, status

@router.post("/aggregate")
async def rebuild_aggregate_skill_gaps(
    db: DbDep, user: CurrentUser
) -> list[SkillGapOut]:
    rows = await MatchService(db).aggregate_skill_gaps(user.id)
    return [_gap_out(g) for g in sorted(rows, key=lambda g: (-g.frequency, g.skill_label))]
```
(200 is the default; no `status_code` needed. The route sorts for a stable response since the freshly-added rows have no DB ordering yet.)

- [ ] **Step 3: `tests/domain/matching/test_aggregate_gaps.py`** (DB-gated) — seed a user + 2 `JobMatch` rows + 3 `scope='job'` `SkillGap` rows (skill A gapped in both matches `important`+`critical`, skill B in one match `nice_to_have`), call `aggregate_skill_gaps`, assert: 2 aggregate rows; skill A `frequency==2`, `severity=='critical'`; skill B `frequency==1`; re-running yields the same 2 (no duplicates). Mirror `tests/api/test_approvals.py` for the `User` seed; for `JobMatch`/`SkillGap` read `app/models/match.py` for required columns (`JobMatch` needs `user_id`, `job_id`, `scorer_version`, `status`; `SkillGap` needs `user_id`, `scope`, `skill_id`, `skill_slug`, `skill_label`, `severity` — `skill_id` needs a real `skills` row, so seed one `Skill` or reuse the taxonomy seed).

- [ ] **Step 4: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`

```bash
git add backend/app/domain/matching/service.py backend/app/api/v1/skill_gaps.py backend/tests/domain/matching/test_aggregate_gaps.py
git commit -m "feat(insights): deterministic skill-gap aggregate rollup + POST /skill-gaps/aggregate"
```

---

## Task 4: `RoadmapPlanner` — SUBAGENT REVIEW

**Files:** Create `backend/app/domain/roadmap/planner.py`, `backend/tests/domain/roadmap/test_planner.py` (DB-gated).

**Interfaces:**
- Consumes: `LearningResource`, `LearningRecommendation`, `RoadmapMilestone`, `SkillGap` (models); `LLMProvider`, `EmbeddingsProvider` (protocols); `_severity_rank`-equivalent ordering.
- Produces: `RoadmapPlanner(session, *, llm, embeddings)` with `async plan(user_id, *, scope, job_id, constraints, publish) -> uuid.UUID`. Module-level `MilestoneDraft` pydantic schema for the LLM call. `_milestone_payload(RoadmapMilestone) -> dict` serialiser (reused by the worker + the SSE replay).

- [ ] **Step 1: `app/domain/roadmap/planner.py`** — implement per spec R4. Skeleton (fill in the SQL + prompt):
```python
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.embeddings.provider import EmbeddingsProvider
from app.domain.llm.provider import LLMMessage, LLMProvider
from app.models.learning import LearningRecommendation, LearningResource, RoadmapMilestone
from app.models.match import SkillGap

log = get_logger("roadmap.planner")

_MAX_MILESTONES = 6
_SEV_RANK = {"critical": 0, "important": 1, "nice_to_have": 2}
Publish = Callable[[dict[str, Any]], Awaitable[None]]


class MilestoneDraft(BaseModel):
    # Loose bounds so the FakeLLMProvider's schema-stub (empty str / 0) validates.
    # `_draft` enforces "is this real content?" in Python and clamps est_hours.
    why_it_matters: str = Field(default="", max_length=600)
    est_hours: int = Field(default=8, ge=0, le=400)
    practice_project: str = Field(default="", max_length=400)
    checkpoint: str = Field(default="", max_length=400)


def _milestone_payload(m: RoadmapMilestone) -> dict[str, Any]:
    return {
        "id": str(m.id), "order_index": m.order_index, "skill_slug": m.skill_slug,
        "skill_label": m.skill_label, "title": m.title, "why_it_matters": m.why_it_matters,
        "resource_ids": [str(r) for r in m.resource_ids], "est_hours": m.est_hours,
        "practice_project": m.practice_project, "checkpoint": m.checkpoint,
        "status": m.status,
    }


class RoadmapPlanner:
    def __init__(
        self, session: AsyncSession, *, llm: LLMProvider, embeddings: EmbeddingsProvider
    ) -> None:
        self._session = session
        self._llm = llm
        self._embeddings = embeddings

    async def plan(
        self,
        user_id: uuid.UUID,
        *,
        scope: str,
        job_id: uuid.UUID | None,
        constraints: dict[str, Any],
        publish: Publish,
    ) -> uuid.UUID:
        rec = (
            await self._session.execute(
                select(LearningRecommendation).where(
                    LearningRecommendation.user_id == user_id,
                    LearningRecommendation.status == "planning",
                ).order_by(LearningRecommendation.created_at.desc())
            )
        ).scalars().first()
        if rec is None:
            raise ValueError("no planning recommendation for user")

        try:
            gaps = await self._top_gaps(user_id)
            n = 0
            for i, gap in enumerate(gaps):
                resources = await self._retrieve(gap)
                draft = await self._draft(gap, resources, constraints)
                if draft is None:
                    continue
                ms = RoadmapMilestone(
                    recommendation_id=rec.id, user_id=user_id, order_index=n,
                    skill_id=gap.skill_id, skill_slug=gap.skill_slug,
                    skill_label=gap.skill_label,
                    title=f"Close your {gap.skill_label} gap",
                    why_it_matters=draft.why_it_matters,
                    resource_ids=[r.id for r in resources],
                    est_hours=draft.est_hours, practice_project=draft.practice_project,
                    checkpoint=draft.checkpoint, status="not_started",
                )
                self._session.add(ms)
                await self._session.flush()
                n += 1
                await publish({"event": "milestone", "milestone": _milestone_payload(ms)})

            rec.status = "active"
            rec.summary = f"{n} milestones to close your top skill gaps."
            first = (
                await self._session.execute(
                    select(RoadmapMilestone)
                    .where(RoadmapMilestone.recommendation_id == rec.id)
                    .order_by(RoadmapMilestone.order_index)
                )
            ).scalars().first()
            rec.next_step = first.title if first is not None else None
            await self._session.flush()
            await publish({"event": "done", "status": "active", "id": str(rec.id)})
            return rec.id
        except Exception as e:  # noqa: BLE001 -- surface as an archived roadmap + SSE error
            log.exception("roadmap_plan_failed", rec_id=str(rec.id))
            rec.status = "archived"
            rec.generation_meta = {**rec.generation_meta, "error": str(e)}
            await self._session.flush()
            # `status: "archived"` so status_stream's terminal check fires for the relay.
            await publish(
                {"event": "error", "status": "archived",
                 "message": "We couldn't build your roadmap."}
            )
            raise

    async def _top_gaps(self, user_id: uuid.UUID) -> list[SkillGap]:
        rows = (
            await self._session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == user_id, SkillGap.scope == "aggregate",
                    SkillGap.status == "open",
                )
            )
        ).scalars().all()
        rows_sorted = sorted(
            rows, key=lambda g: (_SEV_RANK.get(g.severity, 9), -g.frequency)
        )
        return rows_sorted[:_MAX_MILESTONES]

    async def _retrieve(self, gap: SkillGap) -> list[LearningResource]:
        q = await self._embeddings.embed_query(f"Learn {gap.skill_label}")
        rows = (
            await self._session.execute(
                select(LearningResource)
                .where(LearningResource.is_active.is_(True))
                .order_by(LearningResource.embedding.cosine_distance(q))
                .limit(8)
            )
        ).scalars().all()
        overlap = [r for r in rows if gap.skill_slug in (r.skills or [])]
        picked = (overlap or list(rows))[:3]
        return picked

    async def _draft(
        self, gap: SkillGap, resources: list[LearningResource], constraints: dict[str, Any]
    ) -> MilestoneDraft | None:
        if not resources:
            return None
        catalog = "\n".join(
            f"- [{r.id}] {r.title} ({r.provider}, {r.type}, {r.level}) — {r.summary} {r.url}"
            for r in resources
        )
        sys = (
            "You are a pragmatic engineering mentor. Given a skill gap and a short "
            "list of vetted learning resources, produce ONE milestone. Recommend ONLY "
            "from the provided resources. Return strict JSON matching the schema."
        )
        usr = (
            f"Skill gap: {gap.skill_label} (severity {gap.severity}, appears in "
            f"{gap.frequency} of the user's job matches).\n"
            f"Constraints: {constraints or 'none'}.\n\n"
            f"Resources:\n{catalog}\n\n"
            "Write why_it_matters (2-3 sentences, concrete), est_hours (integer), "
            "practice_project (a small buildable thing), checkpoint (how they'll know "
            "they've got it)."
        )
        messages: list[LLMMessage] = [
            {"role": "system", "content": sys},
            {"role": "user", "content": usr},
        ]
        try:
            result = await self._llm.complete(messages, schema=MilestoneDraft, max_tokens=700)
        except Exception:  # noqa: BLE001 -- one bad milestone must not sink the roadmap
            log.warning("roadmap_draft_llm_failed", skill=gap.skill_slug)
            return None
        if result.structured is None:
            return None
        try:
            draft = MilestoneDraft.model_validate(result.structured)
        except Exception:  # noqa: BLE001
            return None
        # "Is this real content?" — the FakeLLMProvider returns empty strings.
        if not draft.why_it_matters.strip() or not draft.practice_project.strip():
            return None
        draft = draft.model_copy(update={"est_hours": max(1, min(draft.est_hours, 200))})
        return draft
```
**NOTES for the implementer:**
- Verify `LearningResource.embedding.cosine_distance(...)` is the pgvector-sqlalchemy operator name against the installed version (grep the repo — `app/domain/rag/vector_store.py` shows how existing code orders by vector distance; mirror that exact call, e.g. `.l2_distance` / `.cosine_distance` / `.max_inner_product`).
- The `fake` LLM provider (test/CI env, `LLM_PROVIDER=fake`) — check what its `complete(..., schema=...)` returns for `structured`. If the fake returns `None`/an empty dict, `_draft` returns `None` and the planner produces **zero** milestones. That is acceptable for CI (the DB-gated test below asserts the `planning→active` transition + `publish` frame sequence, not milestone content). If the fake can be made to echo a valid `MilestoneDraft`, prefer that; do NOT special-case `env == "test"` inside `planner.py`.
- `rec.generation_meta` is a non-null JSONB dict; `{**rec.generation_meta, "error": ...}` is safe.

- [ ] **Step 2: `tests/domain/roadmap/test_planner.py`** (DB-gated) — seed a user, one `Skill`, one `LearningResource` (with a 1024-vector — use `[0.0]*1024` or `seed_learning_resources`), one `scope='aggregate'` open `SkillGap`, and a `LearningRecommendation(status='planning')`. Build a `publish` that appends frames to a list. Run `RoadmapPlanner(db_session, llm=get_llm_provider(get_settings()), embeddings=get_embeddings_provider(get_settings())).plan(user_id, scope="aggregate", job_id=None, constraints={}, publish=collect)`. Assert: the recommendation ends `status='active'`; the last `publish` frame is `{"event": "done", ...}` (or, if the fake LLM yields no draft, still `done` with 0 milestones); no exception.

- [ ] **Step 3: gate + commit**

```bash
git add backend/app/domain/roadmap/planner.py backend/tests/domain/roadmap/test_planner.py
git commit -m "feat(insights): RoadmapPlanner -- retrieve catalog + per-milestone LLM, stream via publish"
```

---

## Task 5: `RoadmapService` + `plan_roadmap` worker task + wiring — SUBAGENT REVIEW

**Files:** Create `backend/app/domain/roadmap/service.py`, `backend/app/worker/tasks/roadmap.py`. Modify `backend/app/core/events.py`, `backend/app/worker/tasks/__init__.py`, `backend/app/worker/main.py`, `backend/tests/conftest.py`. Create `backend/tests/worker/test_plan_roadmap_task.py` (DB-gated).

**Interfaces:**
- Consumes: `RoadmapPlanner` (Task 4), `enqueue` (`app.core.queue`), `roadmap_channel`.
- Produces: `RoadmapService(session)` with `create(user_id, *, scope, job_id, constraints) -> LearningRecommendation` (row + enqueue), `list_(user_id) -> list[LearningRecommendation]`, `get(user_id, rec_id) -> LearningRecommendation`, `milestones(rec_id) -> list[RoadmapMilestone]`, `set_status(user_id, rec_id, status) -> LearningRecommendation`, `set_milestone_status(user_id, rec_id, milestone_id, status) -> RoadmapMilestone`. Worker `plan_roadmap(ctx, rec_id: str) -> None`. `roadmap_channel(rec_id: str) -> str`.

- [ ] **Step 1: `app/core/events.py`** — add next to `job_channel`:
```python
def roadmap_channel(rec_id: str) -> str:
    return f"sse:roadmap:{rec_id}"
```

- [ ] **Step 2: `app/domain/roadmap/service.py`**
```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.core.queue import enqueue
from app.models.learning import LearningRecommendation, RoadmapMilestone
from app.models.match import SkillGap

_REC_STATUS = {"active", "archived"}
_MS_STATUS = {"not_started", "in_progress", "done"}


class RoadmapService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, user_id: uuid.UUID, *, scope: str, job_id: uuid.UUID | None,
        constraints: dict[str, Any], title: str,
    ) -> LearningRecommendation:
        rec = LearningRecommendation(
            user_id=user_id, scope=scope, job_id=job_id, title=title,
            constraints=constraints, status="planning",
        )
        self._session.add(rec)
        await self._session.flush()
        return rec

    async def enqueue_plan(self, rec_id: uuid.UUID) -> None:
        await enqueue("plan_roadmap", str(rec_id), _job_id=f"plan_roadmap:{rec_id}")

    async def list_(self, user_id: uuid.UUID) -> list[LearningRecommendation]:
        rows = (
            await self._session.execute(
                select(LearningRecommendation)
                .where(LearningRecommendation.user_id == user_id)
                .order_by(LearningRecommendation.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def get(self, user_id: uuid.UUID, rec_id: uuid.UUID) -> LearningRecommendation:
        rec = (
            await self._session.execute(
                select(LearningRecommendation).where(
                    LearningRecommendation.id == rec_id,
                    LearningRecommendation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if rec is None:
            raise NotFoundError(detail="Roadmap not found")
        return rec

    async def milestones(self, rec_id: uuid.UUID) -> list[RoadmapMilestone]:
        rows = (
            await self._session.execute(
                select(RoadmapMilestone)
                .where(RoadmapMilestone.recommendation_id == rec_id)
                .order_by(RoadmapMilestone.order_index)
            )
        ).scalars().all()
        return list(rows)

    async def set_status(
        self, user_id: uuid.UUID, rec_id: uuid.UUID, status: str
    ) -> LearningRecommendation:
        if status not in _REC_STATUS:
            raise ValidationAppError(f"Can't set roadmap status to {status!r}.")
        rec = await self.get(user_id, rec_id)
        rec.status = status
        await self._session.flush()
        return rec

    async def set_milestone_status(
        self, user_id: uuid.UUID, rec_id: uuid.UUID, milestone_id: uuid.UUID, status: str
    ) -> RoadmapMilestone:
        if status not in _MS_STATUS:
            raise ValidationAppError(f"Can't set milestone status to {status!r}.")
        await self.get(user_id, rec_id)  # ownership + 404
        ms = (
            await self._session.execute(
                select(RoadmapMilestone).where(
                    RoadmapMilestone.id == milestone_id,
                    RoadmapMilestone.recommendation_id == rec_id,
                )
            )
        ).scalar_one_or_none()
        if ms is None:
            raise NotFoundError(detail="Milestone not found")

        was_done = ms.status == "done"
        ms.status = status
        if status == "done":
            ms.completed_at = datetime.now(UTC)
            await self._session.execute(
                update(SkillGap)
                .where(
                    SkillGap.user_id == user_id, SkillGap.scope == "aggregate",
                    SkillGap.skill_slug == ms.skill_slug,
                )
                .values(status="closed", addressed_by_roadmap_id=rec_id)
            )
        elif was_done:
            ms.completed_at = None
            await self._session.execute(
                update(SkillGap)
                .where(
                    SkillGap.user_id == user_id, SkillGap.scope == "aggregate",
                    SkillGap.skill_slug == ms.skill_slug,
                )
                .values(status="open", addressed_by_roadmap_id=None)
            )
        await self._session.flush()
        return ms
```
**NOTE:** `create` and `enqueue_plan` are separate so the route can `create → commit → enqueue_plan` (the row must be committed before the worker reads it). `enqueue` is imported at module level so conftest can patch `app.domain.roadmap.service.enqueue`.

- [ ] **Step 3: `app/worker/tasks/roadmap.py`**
```python
from __future__ import annotations

import json
import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.events import roadmap_channel
from app.core.logging import get_logger
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.llm.factory import get_llm_provider
from app.domain.roadmap.planner import RoadmapPlanner
from app.models.learning import LearningRecommendation

log = get_logger("worker.roadmap")


async def plan_roadmap(ctx: dict[str, Any], rec_id: str) -> None:
    # Mirrors app/worker/tasks/agent.py::_run_or_resume — own Redis conn +
    # aclose() in finally; ARQ's ctx does NOT carry a redis pool in this repo.
    log.info("plan_roadmap_start", rec_id=rec_id, job_id=ctx.get("job_id"))
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    channel = roadmap_channel(rec_id)

    async def publish(frame: dict[str, Any]) -> None:
        await redis.publish(channel, json.dumps(frame, default=str))

    try:
        async with AsyncSessionLocal() as session:
            rec = (
                await session.execute(
                    select(LearningRecommendation).where(
                        LearningRecommendation.id == uuid.UUID(rec_id)
                    )
                )
            ).scalar_one_or_none()
            if rec is None or rec.status != "planning":
                log.info("plan_roadmap_skipped", rec_id=rec_id,
                         reason="missing" if rec is None else rec.status)
                return
            planner = RoadmapPlanner(
                session,
                llm=get_llm_provider(settings),
                embeddings=get_embeddings_provider(settings),
            )
            try:
                await planner.plan(
                    rec.user_id, scope=rec.scope, job_id=rec.job_id,
                    constraints=dict(rec.constraints), publish=publish,
                )
            finally:
                # planner.plan() sets status active/archived on its own session;
                # commit either outcome so the row + milestones persist.
                await session.commit()
    finally:
        await redis.aclose()
```
**NOTE for the implementer:** `ctx` is referenced via the opening `log.info(... job_id=ctx.get("job_id"))` line (matches `app/worker/tasks/ping.py`), so no `ARG001` issue. `from __future__ import annotations` at the top of the file.

- [ ] **Step 4: wire the worker** — `app/worker/tasks/__init__.py`: add `from app.worker.tasks.roadmap import plan_roadmap` and `"plan_roadmap"` into `__all__` (keep it sorted — it goes after `parse_resume`, before `ping`... actually alphabetical: `..., "parse_resume", "ping", "plan_roadmap", "resume_agent", ...` — `ping` < `plan_roadmap` since `pi` < `pl`). `app/worker/main.py`: add `plan_roadmap` to the `from app.worker.tasks import (...)` tuple and to `WorkerSettings.functions`.

- [ ] **Step 5: `tests/conftest.py`** — add to `_no_enqueue`:
```python
    monkeypatch.setattr("app.domain.roadmap.service.enqueue", _noop, raising=False)
```

- [ ] **Step 6: `tests/worker/test_plan_roadmap_task.py`** (DB-gated) — seed as in Task 4's test, insert the `LearningRecommendation(status='planning')`, build a fake `ctx` with a `redis` object whose `.publish` appends `(channel, json.loads(msg))` to a list (mirror `tests/conftest.py::fake_redis` — extend it if needed), call `await plan_roadmap(ctx, str(rec.id))`, assert the recommendation is `status='active'` (or `archived` only if the fake LLM path raised — it must not) and that a `done` frame was published on `sse:roadmap:{rec_id}`.

- [ ] **Step 7: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
(`lint-imports` must stay `3 kept, 0 broken` — `roadmap/service.py` imports only `app.core.*` + `app.models.*`; `worker/tasks/roadmap.py` is in the `app.worker` layer so it may import `app.domain.*`.)

```bash
git add backend/app/domain/roadmap/service.py backend/app/worker/tasks/roadmap.py backend/app/core/events.py backend/app/worker/tasks/__init__.py backend/app/worker/main.py backend/tests/conftest.py backend/tests/worker/test_plan_roadmap_task.py
git commit -m "feat(insights): RoadmapService + plan_roadmap worker task + sse:roadmap channel"
```

---

## Task 6: `/roadmaps` API + schemas

**Files:** Create `backend/app/api/v1/roadmaps.py`, `backend/app/api/v1/schemas/roadmaps.py`. Modify `backend/app/api/v1/router.py`. Create `backend/tests/api/test_roadmaps.py` (DB-gated).

**Interfaces:**
- Consumes: `RoadmapService` (Task 5), `_milestone_payload` (Task 4 — import from `app.domain.roadmap.planner`).
- Produces: `POST /roadmaps` (202), `GET /roadmaps`, `GET /roadmaps/{id}`, `PATCH /roadmaps/{id}`, `PATCH /roadmaps/{id}/milestones/{mid}`. (SSE + `/learning-resources` are Task 7.)

- [ ] **Step 1: `app/api/v1/schemas/roadmaps.py`**
```python
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RoadmapCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(default="aggregate", pattern=r"^(aggregate|job)$")
    job_id: uuid.UUID | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class RoadmapRefOut(BaseModel):
    id: uuid.UUID


class RoadmapOut(BaseModel):
    id: uuid.UUID
    scope: str
    job_id: uuid.UUID | None
    title: str
    summary: str | None
    next_step: str | None
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class MilestoneOut(BaseModel):
    id: uuid.UUID
    order_index: int
    skill_slug: str
    skill_label: str
    title: str
    why_it_matters: str
    resource_ids: list[uuid.UUID]
    est_hours: int | None
    practice_project: str | None
    checkpoint: str | None
    status: str
    completed_at: dt.datetime | None


class RoadmapDetailOut(RoadmapOut):
    milestones: list[MilestoneOut]


class RoadmapListOut(BaseModel):
    items: list[RoadmapOut]


class RoadmapPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^(active|archived)$")


class MilestonePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^(not_started|in_progress|done)$")
```

- [ ] **Step 2: `app/api/v1/roadmaps.py`**
```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.roadmaps import (
    MilestoneOut,
    MilestonePatchIn,
    RoadmapCreateIn,
    RoadmapDetailOut,
    RoadmapListOut,
    RoadmapOut,
    RoadmapPatchIn,
    RoadmapRefOut,
)
from app.domain.roadmap.service import RoadmapService
from app.models.job import Job
from app.models.learning import LearningRecommendation, RoadmapMilestone

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])


def _roadmap_out(r: LearningRecommendation) -> RoadmapOut:
    return RoadmapOut(
        id=r.id, scope=r.scope, job_id=r.job_id, title=r.title, summary=r.summary,
        next_step=r.next_step, status=r.status,
        created_at=r.created_at, updated_at=r.updated_at,
    )


def _milestone_out(m: RoadmapMilestone) -> MilestoneOut:
    return MilestoneOut(
        id=m.id, order_index=m.order_index, skill_slug=m.skill_slug,
        skill_label=m.skill_label, title=m.title, why_it_matters=m.why_it_matters,
        resource_ids=list(m.resource_ids), est_hours=m.est_hours,
        practice_project=m.practice_project, checkpoint=m.checkpoint,
        status=m.status, completed_at=m.completed_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_roadmap(
    body: RoadmapCreateIn, db: DbDep, user: CurrentUser
) -> RoadmapRefOut:
    title = "Learning roadmap"
    if body.job_id is not None:
        job = (
            await db.execute(
                select(Job).where(Job.id == body.job_id)  # noqa: F821 -- add the import
            )
        ).scalar_one_or_none()
        if job is not None and job.title:
            title = f"Roadmap for {job.title}"
    svc = RoadmapService(db)
    rec = await svc.create(
        user.id, scope=body.scope, job_id=body.job_id,
        constraints=body.constraints, title=title,
    )
    await db.commit()
    await svc.enqueue_plan(rec.id)
    return RoadmapRefOut(id=rec.id)


@router.get("")
async def list_roadmaps(db: DbDep, user: CurrentUser) -> RoadmapListOut:
    rows = await RoadmapService(db).list_(user.id)
    return RoadmapListOut(items=[_roadmap_out(r) for r in rows])


@router.get("/{roadmap_id}")
async def get_roadmap(
    roadmap_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> RoadmapDetailOut:
    svc = RoadmapService(db)
    rec = await svc.get(user.id, roadmap_id)
    ms = await svc.milestones(roadmap_id)
    return RoadmapDetailOut(
        **_roadmap_out(rec).model_dump(),
        milestones=[_milestone_out(m) for m in ms],
    )


@router.patch("/{roadmap_id}")
async def patch_roadmap(
    roadmap_id: uuid.UUID, body: RoadmapPatchIn, db: DbDep, user: CurrentUser
) -> RoadmapOut:
    return _roadmap_out(
        await RoadmapService(db).set_status(user.id, roadmap_id, body.status)
    )


@router.patch("/{roadmap_id}/milestones/{milestone_id}")
async def patch_milestone(
    roadmap_id: uuid.UUID, milestone_id: uuid.UUID, body: MilestonePatchIn,
    db: DbDep, user: CurrentUser,
) -> MilestoneOut:
    return _milestone_out(
        await RoadmapService(db).set_milestone_status(
            user.id, roadmap_id, milestone_id, body.status
        )
    )
```
**NOTE for the implementer:** add `from sqlalchemy import select` to the imports (the `create_roadmap` job-title lookup uses it — the `# noqa: F821` marker in the skeleton is a reminder, remove it once the import is real). Confirm `RoadmapDetailOut(**_roadmap_out(rec).model_dump(), milestones=...)` type-checks under mypy strict; if it complains, construct `RoadmapDetailOut` field-by-field instead.

- [ ] **Step 3: `app/api/v1/router.py`** — add `roadmaps` to the `from app.api.v1 import (...)` block (alphabetical: after `resumes`? no — `roadmaps` < `resumes` is false; `roadmaps` vs `resumes`: `roa` < `res` is false, `res` < `roa`... compare char 2: `o` vs `e` → `e` < `o`, so `resumes` < `roadmaps`. Insert `roadmaps` after `resumes`, before `skill_gaps`) and `api_router.include_router(roadmaps.router)`.

- [ ] **Step 4: `tests/api/test_roadmaps.py`** (DB-gated) — `_auth` helper (mirror `test_approvals.py`); seed a `Skill` + an aggregate `SkillGap` + a `LearningResource`. `POST /api/v1/roadmaps {}` → 202, body has `id`. (`_no_enqueue` stops the real task.) Then directly insert milestones (or call the service) and test `GET /api/v1/roadmaps`, `GET /{id}` (has `milestones`), `PATCH /{id} {status:"archived"}` → 200, `PATCH /{id}/milestones/{mid} {status:"done"}` → 200 + the aggregate gap for that skill flips to `closed`. `PATCH` with `status:"planning"` → 422 (pattern reject).

- [ ] **Step 5: gate + commit**

```bash
git add backend/app/api/v1/roadmaps.py backend/app/api/v1/schemas/roadmaps.py backend/app/api/v1/router.py backend/tests/api/test_roadmaps.py
git commit -m "feat(insights): /roadmaps API -- create/list/get/patch/milestone-patch"
```

---

## Task 7: `/roadmaps/{id}/events` SSE relay + `/learning-resources`

**Files:** Modify `backend/app/api/v1/roadmaps.py`, `backend/app/api/v1/schemas/roadmaps.py`. Create `backend/app/api/v1/schemas/learning.py`. Modify `backend/app/api/v1/router.py`. Create `backend/tests/domain/roadmap/test_events_gen.py` (pure — tests the generator, per `sse-tests-asgitransport-buffers` memory) + extend `tests/api/test_roadmaps.py` for `/learning-resources`.

**Interfaces:**
- Consumes: `roadmap_channel`, `status_stream`, `sse_event`, `AsyncSessionLocal`, `_milestone_payload`.
- Produces: `GET /roadmaps/{id}/events` (SSE), `GET /learning-resources`.

- [ ] **Step 1: SSE relay in `roadmaps.py`** — mirror `app/api/v1/jobs.py::job_events` closely. Read it first. Add imports: `from collections.abc import AsyncIterator`, `from sse_starlette import EventSourceResponse, ServerSentEvent`, `from app.api.deps import RedisDep`, `from app.core.db import AsyncSessionLocal`, `from app.core.events import roadmap_channel, sse_event, status_stream`, `from app.domain.roadmap.planner import _milestone_payload`.
```python
@router.get("/{roadmap_id}/events")
async def roadmap_events(
    roadmap_id: uuid.UUID, user: CurrentUser, redis: RedisDep
) -> EventSourceResponse:
    async with AsyncSessionLocal() as session:
        await RoadmapService(session).get(user.id, roadmap_id)  # 404s non-owners

    async def _gen() -> AsyncIterator[ServerSentEvent]:
        async for payload in status_stream(
            redis, roadmap_channel(str(roadmap_id)), terminal={"active", "archived"}
        ):
            if payload.get("event") == "open":
                # Replay whatever the planner has already written so a late
                # subscriber still gets the full picture.
                async with AsyncSessionLocal() as s:
                    svc = RoadmapService(s)
                    try:
                        rec = await svc.get(user.id, roadmap_id)
                    except NotFoundError:
                        return
                    for m in await svc.milestones(roadmap_id):
                        yield sse_event({"event": "milestone", "milestone": _milestone_payload(m)})
                    if rec.status in {"active", "archived"}:
                        yield sse_event({"event": "done", "status": rec.status, "id": str(roadmap_id)})
                        return
                continue
            yield sse_event(payload)

    return EventSourceResponse(_gen())
```
**NOTE:** `status_stream`'s `terminal` check keys on `payload.get("status")`; the planner's `done`/`error` frames use `event` not `status`. Check `jobs.py`'s exact loop — the planner should also publish a `status` key on its terminal frames (`{"event": "done", "status": "active", ...}` already does; make the `error` frame `{"event": "error", "status": "archived", "message": ...}` so `status_stream` terminates). Update `RoadmapPlanner`'s error `publish(...)` in Task 4 accordingly if it isn't already — record this as a cross-task fixup in the ledger.

- [ ] **Step 2: `app/api/v1/schemas/learning.py`**
```python
from __future__ import annotations

import uuid

from pydantic import BaseModel


class LearningResourceOut(BaseModel):
    id: uuid.UUID
    title: str
    provider: str
    url: str
    type: str
    skills: list[str]
    level: str
    est_hours: int | None
    cost: str
    summary: str
```

- [ ] **Step 3: `/learning-resources` route** — its own small router in `roadmaps.py` (or a new `learning.py`). Add:
```python
lr_router = APIRouter(prefix="/learning-resources", tags=["learning-resources"])


@lr_router.get("")
async def list_learning_resources(
    db: DbDep, user: CurrentUser, skills: str | None = None, level: str | None = None
) -> list[LearningResourceOut]:
    stmt = select(LearningResource).where(LearningResource.is_active.is_(True))
    slugs = [s for s in (skills or "").split(",") if s]
    if slugs:
        stmt = stmt.where(LearningResource.skills.op("&&")(slugs))
    if level is not None:
        stmt = stmt.where(LearningResource.level == level)
    stmt = stmt.order_by(LearningResource.level, LearningResource.est_hours.nulls_last()).limit(50)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        LearningResourceOut(
            id=r.id, title=r.title, provider=r.provider, url=r.url, type=r.type,
            skills=list(r.skills), level=r.level, est_hours=r.est_hours, cost=r.cost,
            summary=r.summary,
        )
        for r in rows
    ]
```
Register `lr_router` in `router.py` too (`api_router.include_router(roadmaps.lr_router)`).
**NOTE:** verify the array-overlap operator — `LearningResource.skills.op("&&")(slugs)` needs the RHS to be a Postgres `text[]`; if mypy/pg complains, use `LearningResource.skills.overlap(slugs)` (the SQLAlchemy `ARRAY` comparator method) — grep the repo for an existing `&&` / `.overlap(` usage (jobs filtering may have one) and mirror it.

- [ ] **Step 4: `tests/domain/roadmap/test_events_gen.py`** — a pure test that drives `roadmap_events`'s inner generator is hard (it needs `redis` + a session); instead do a DB-gated test in `test_roadmaps.py` that asserts `GET /roadmaps/{id}/events` returns `200` with `content-type: text/event-stream` for the owner and `404` for a non-owner (do NOT consume the stream — the ownership check happens before the first yield; per the `sse-tests-asgitransport-buffers` memory, don't try to read frames through the test client). Add `/learning-resources` assertions: seed 2 resources (one `sql`, one `rust`), `GET /api/v1/learning-resources?skills=sql` returns only the sql one; `?level=beginner` filters by level.

- [ ] **Step 5: gate + commit**

```bash
git add backend/app/api/v1/roadmaps.py backend/app/api/v1/schemas/roadmaps.py backend/app/api/v1/schemas/learning.py backend/app/api/v1/router.py backend/tests/api/test_roadmaps.py backend/tests/domain/roadmap
git commit -m "feat(insights): roadmap SSE relay + GET /learning-resources"
```

---

## Task 8: `/insights` composition

**Files:** Create `backend/app/domain/insights/__init__.py`, `backend/app/domain/insights/ranker.py`, `backend/app/domain/insights/service.py`, `backend/app/api/v1/insights.py`, `backend/app/api/v1/schemas/insights.py`. Modify `backend/app/api/v1/router.py`. Create `backend/tests/domain/insights/test_insights_service.py` + `backend/tests/api/test_insights.py` (DB-gated).

**Interfaces:**
- Consumes: `SkillGap`, `JobMatch`, `Job`, `Application`, `LearningRecommendation`, `RoadmapMilestone` (models); `MatchService.aggregate_skill_gaps` for the lazy rollup.
- Produces: `next_best_action(session, user_id) -> NextStep | None`; `InsightsService(session).compose(user_id) -> InsightsOut`.

- [ ] **Step 1: schemas `app/api/v1/schemas/insights.py`**
```python
from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.api.v1.schemas.skill_gaps import SkillGapOut


class SkillMention(BaseModel):
    skill_slug: str
    skill_label: str
    detail: str | None


class NextStep(BaseModel):
    kind: str
    title: str
    reason: str
    entity_type: str | None
    entity_id: uuid.UUID | None


class RoadmapSummary(BaseModel):
    id: uuid.UUID
    title: str
    next_step: str | None
    milestones_done: int
    milestones_total: int


class InsightsOut(BaseModel):
    strengths: list[SkillMention]
    skills_to_develop: list[SkillGapOut]
    recommended_next_step: NextStep | None
    trending_skills: list[SkillMention]
    suggested_projects: list[str]
    roadmap_summary: RoadmapSummary | None
```

- [ ] **Step 2: `app/domain/insights/ranker.py`** — `async def next_best_action(session, user_id) -> NextStepData | None` where `NextStepData` is a frozen dataclass `{kind, title, reason, entity_type: str|None, entity_id: uuid.UUID|None}`. Implement the 5 ordered rules from spec R7 (a→e) with direct `select(...)` queries against `Application` (status `awaiting_approval`; `applied` + stale 14d), `JobMatch` (count), `SkillGap` (aggregate count), `LearningRecommendation`+`RoadmapMilestone` (active rec with a `not_started` milestone), `Job` (count `user_id == user_id`). First rule that fires wins; else `None`.

- [ ] **Step 3: `app/domain/insights/service.py`** — `InsightsService(session).compose(user_id) -> InsightsData` (a dataclass mirroring `InsightsOut`'s fields, mapped in the route). Logic per spec R7. For the lazy aggregate rollup: `InsightsService` must NOT import `MatchService` (sibling domain). Instead inline the same delete-then-insert rollup as a private helper, OR (simpler) have the route call `MatchService(db).aggregate_skill_gaps(user.id)` when `skills_to_develop` would be empty and `JobMatch` count > 0, then re-query. **Ruling for the implementer: do the lazy rollup in the ROUTE** (`app.api` may import both services), keeping `InsightsService` a pure reader. Cap lists per spec (strengths 6, skills_to_develop 8, trending 10, projects 4).

- [ ] **Step 4: `app/api/v1/insights.py`**
```python
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.insights import (
    InsightsOut, NextStep, RoadmapSummary, SkillMention,
)
from app.api.v1.schemas.skill_gaps import SkillGapOut
from app.domain.insights.ranker import next_best_action
from app.domain.insights.service import InsightsService
from app.domain.matching.service import MatchService
from app.models.match import JobMatch  # count for the lazy-rollup guard
from sqlalchemy import func, select

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("")
async def get_insights(db: DbDep, user: CurrentUser) -> InsightsOut:
    # Lazy aggregate rollup: first Insights view after scoring has no aggregate rows.
    agg_count = (
        await db.execute(
            select(func.count()).select_from(...)  # SkillGap where user + scope aggregate
        )
    ).scalar_one()
    match_count = (
        await db.execute(select(func.count()).select_from(JobMatch).where(JobMatch.user_id == user.id))
    ).scalar_one()
    if agg_count == 0 and match_count > 0:
        await MatchService(db).aggregate_skill_gaps(user.id)

    data = await InsightsService(db).compose(user.id)
    nba = await next_best_action(db, user.id)
    return InsightsOut(
        strengths=[SkillMention(**s.__dict__) for s in data.strengths],
        skills_to_develop=[SkillGapOut(**g) for g in data.skills_to_develop],
        recommended_next_step=(
            NextStep(kind=nba.kind, title=nba.title, reason=nba.reason,
                     entity_type=nba.entity_type, entity_id=nba.entity_id)
            if nba is not None else None
        ),
        trending_skills=[SkillMention(**s.__dict__) for s in data.trending_skills],
        suggested_projects=data.suggested_projects,
        roadmap_summary=(
            RoadmapSummary(**data.roadmap_summary.__dict__)
            if data.roadmap_summary is not None else None
        ),
    )
```
**NOTE for the implementer:** finish the `agg_count` query (`select(func.count()).select_from(SkillGap).where(SkillGap.user_id == user.id, SkillGap.scope == "aggregate")`). Pick clean dataclass↔schema mapping — if `**s.__dict__` is fragile under mypy, map fields explicitly. `data.skills_to_develop` should already be `list[dict]` shaped like `_gap_out` output, or map from `SkillGap` rows via the existing `_gap_out` in `skill_gaps.py` (import it).

- [ ] **Step 5: `router.py`** — add `insights` to the import block (alphabetical: after `health`, before `jobs`) + `api_router.include_router(insights.router)`.

- [ ] **Step 6: tests** — `test_insights_service.py` (DB-gated): seed a user with 1 job match (strengths jsonb populated), 2 aggregate gaps, 1 tracked job, an active recommendation with 2 milestones (1 `not_started`) → assert `compose` returns the expected caps + `roadmap_summary.milestones_total == 2`, `milestones_done == 0`. `test_insights.py` (DB-gated): `GET /api/v1/insights` for a fresh user → `200`, all six keys present, `recommended_next_step` is either `null` or a `{kind,title,reason}` object; for a user with `≥1` match and no aggregate rows → the response's `skills_to_develop` is non-empty (lazy rollup fired).

- [ ] **Step 7: gate + commit**

```bash
git add backend/app/domain/insights backend/app/api/v1/insights.py backend/app/api/v1/schemas/insights.py backend/app/api/v1/router.py backend/tests/domain/insights backend/tests/api/test_insights.py
git commit -m "feat(insights): GET /insights -- strengths/gaps/next-step/trending/projects/roadmap composition"
```

---

## Task 9: DB-gated integration sweep — SUBAGENT REVIEW

**Files:** Create `backend/tests/api/test_insights_flow.py`.

**Interfaces:** Consumes the whole phase. No production code.

- [ ] **Step 1:** one end-to-end DB-gated test that exercises the realistic chain with the `client` + `db_session` fixtures and the `_no_enqueue` autouse patch:
  1. register+login (`_auth`), seed 1 `Skill` + 2 seed `Job`s + score-free `JobMatch` rows with `scope='job'` `SkillGap`s.
  2. `POST /api/v1/skill-gaps/aggregate` → 200, ≥1 aggregate row.
  3. `POST /api/v1/roadmaps {}` → 202 `{id}`.
  4. Because `_no_enqueue` stubbed the task, drive the planner directly: `await RoadmapPlanner(db_session, llm=get_llm_provider(get_settings()), embeddings=get_embeddings_provider(get_settings())).plan(user_id, scope="aggregate", job_id=None, constraints={}, publish=_collect)` — assert it reaches `status='active'`.
  5. `GET /api/v1/roadmaps/{id}` → milestones present (or empty if the fake LLM yields none — assert the recommendation shape either way).
  6. `PATCH /api/v1/roadmaps/{id}/milestones/{mid} {status:"done"}` (only if a milestone exists) → the aggregate `SkillGap` for that skill is `closed`.
  7. `GET /api/v1/insights` → 200, `roadmap_summary` non-null, `skills_to_develop` reflects the aggregate.

- [ ] **Step 2: gate**

```bash
git add backend/tests/api/test_insights_flow.py
git commit -m "test(insights): end-to-end aggregate -> roadmap -> insights flow (DB-gated)"
```

---

## Task 10: verification + whole-branch review + completion report + squash + push + CI

Controller-only. Mirror the Phase 11a closeout: full local gate; run every pure suite added (`tests/domain/roadmap/test_catalog_json.py` at least); whole-branch review (inline except Tasks 1/4/5/9 which had subagent reviews — the whole-branch pass is still a fresh read of `<fork>..HEAD` for cross-task integration, esp. the planner `done`/`error` frame `status` key vs `status_stream`'s terminal check, the `lint-imports` contract, and the migration `0015` head); directly-verified baseline counts (checkout the fork commit, `pytest --collect-only` + `mypy app`, restore); append the completion report to this plan file; squash/fast-forward to `main`; push; watch CI (the `backend` job's real-Postgres DB suite is the proof — watch for: `0015` applying, the HNSW index on `learning_resources.embedding`, the `cosine_distance`/`overlap` operators against real pgvector, and the `fake` LLM path through `RoadmapPlanner` not raising); `finishing-a-development-branch`; update `mana-career-roadmap-progress` memory.
