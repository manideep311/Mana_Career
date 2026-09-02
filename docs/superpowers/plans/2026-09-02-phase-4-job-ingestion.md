# Phase 4: Job Ingestion + Search — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A browsable job corpus — a fresh clone shows ~40 demo postings on a Discovery page with search + filters; a signed-in user can paste a job description and watch it become a structured Job Detail record.

**Architecture:** Mirrors the résumé pipeline. `POST /jobs {raw_text}` inserts a `jobs` row (`status="ingesting"`) and enqueues one ARQ task `ingest_job`, which cleans the text (`JobIngestor`), extracts structure via one LLM call (`JobExtractor` → `JobExtraction` Pydantic model), maps required/preferred skill strings onto the Phase 3 taxonomy (`SkillNormalizer`), section-chunks the JD (`chunk_job`), embeds each chunk (`get_embeddings_provider`), persists everything, and publishes SSE `status`/`done`/`error` on `job:<id>`. Discovery `GET /jobs` is plain Postgres — a generated `search_tsv` column (`websearch_to_tsquery`) + `pg_trgm` on title/company + `WHERE` filters + `sort=recent`. `job_chunks` is populated now; the retriever over it is Phase 6. Seed jobs are hand-authored **pre-structured** rows (skip the extractor, `status="ready"`), still chunked + embedded at seed time.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, ARQ + Redis, pgvector (`Vector`, `.cosine_distance()`), Pydantic v2, structlog. Frontend: Next.js 15 App Router, React 19, TS strict, Tailwind v4, `@tanstack/react-query` v5, `react-hook-form` + `zod`, `lucide-react`, Vitest + Testing Library + jsdom.

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` (§1.7 job data-model decision, §2.2 `/jobs` routes, §5 `jobs` + `job_chunks` tables, §6.4 SSE contract, §7.1 route map).

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtimes:** Python 3.12; PostgreSQL 16 + `pgvector` + `pg_trgm` (both already enabled by `0001_bootstrap.py`); Redis 7. Migration chain: `0006_skills` is head → this phase adds `0007_jobs`.
- **PKs / timestamps / enums / soft-delete / audit:** exactly as Phases 1–3 — `uuid` `server_default=text("gen_random_uuid()")`; `created_at`/`updated_at` from `TimestampMixin` + a `set_updated_at()` trigger created in the migration; enums as `text` + named `CHECK`; `deleted_at timestamptz` soft-delete on user rows; `import-linter` layers `api > worker > domain > infra > core > models`, `domain/*` never imports `api`/`worker`.
- **Jobs ownership model (spec §5, §6.3):** `jobs.user_id` is **nullable** — `NULL` = the shared seed dataset. This is the one user-scoped table that deviates from "`user_id NOT NULL`". Every read filter is `(user_id = :me OR user_id IS NULL) AND deleted_at IS NULL`. `PATCH`/`DELETE` act on `user_id = :me` rows only (never seed rows). `is_seed` boolean is the fast discriminator.
- **Source vocab (spec §26 / §5):** `jobs.source ∈ {user_paste, user_upload, seed}`. Phase 4 only ever writes `user_paste` (API) and `seed` (seed loader); `user_upload` is a valid CHECK value reserved for the deferred file-upload path.
- **Embeddings:** all vector work goes through `get_embeddings_provider(settings)` (`app.domain.embeddings.factory`). CI runs `EMBEDDINGS_PROVIDER=fake`, `EMBED_DIM=1024`; `FakeEmbeddingsProvider` returns a deterministic unit vector keyed on the exact text (sha256 → seeded RNG). Store `embed_model` + `embed_dim` on every `job_chunks` row. `Vector(1024)` literal in the model + migration must match `settings.embed_dim` (default 1024) — add the same sync comment Phase 3's `models/skill.py` carries.
- **LLM:** all extraction goes through `get_llm_provider(settings)` with `model=settings.llm_model_extraction`. CI runs `LLM_PROVIDER=fake`; `FakeLLMProvider.complete(schema=X)` returns `X` with every field stubbed (`None` / `[]` / `0` / `""`), so a fake extraction is a *valid but empty* `JobExtraction`.
- **Indexes (spec §5 datastore rules):** HNSW (`m=16, ef_construction=64`, `postgresql_ops={"embedding": "vector_cosine_ops"}`) on every embedding column; GIN on `tsvector` columns and on `jsonb` filter columns; `pg_trgm` GIN (`gin_trgm_ops`) on `jobs.title` and `jobs.company`.
- **Money:** integer whole-currency units + `salary_currency` (3-char) + `salary_period ∈ {year, month, day, hour}` (spec §5).
- **SSE (spec §6.4):** events `status {resource, id, status, message}`, `done {status, totals}`, `error {code, message}`. Reuse `app/core/events.py` (`publish_status`, `status_stream`, `sse_event`); add a `job_channel(job_id)` helper next to `resume_channel`.
- **Rate limits (spec §6.5):** `POST /jobs` is already routed to the `upload` tier by `app/core/rate_limit.py::_bucket` (`f"{base}/jobs"` is hard-coded there) — no rate-limit change needed. `upload_limit_per_hour = 20`.
- **Worker retry discipline (Phase 3 lesson):** the `except` block in `ingest_job` guards `if ctx.get("job_try", 1) < MAX_TRIES: raise` **before** `record_failure(...)`, exactly like `app/worker/tasks/resume.py`. Import `MAX_TRIES` from `app.worker.tasks.resume` (as `worker/main.py` already does).
- **Session seam:** `ingest_job`'s module carries a **verbatim copy** of the `_session_for()` async-CM from `app/worker/tasks/resume.py` (not an import — keeps task modules decoupled; the DB test monkeypatches `app.worker.tasks.jobs._session_for`).
- **Demo dataset:** spec §1.7 says "~60–100"; Phase 4 ships **~40 hand-authored pre-structured rows** (approved scope decision — enough to exercise every filter, no LLM dependency at seed). Manual-only ingestion, **no scraping / no job-board APIs** (§1.7).
- **Deferred, flagged in the relevant task:** `POST/GET /jobs/{id}/research` (Phase 7 Job Research Agent); match % on cards, `has_match` filter, `sort=match` (Phase 5 — params are accepted and documented as no-op); file/PDF JD upload (`source="user_upload"`, `POST /jobs` multipart — paste-only for now); hybrid/vector Discovery search (Phase 6 — `job_chunks` is *populated* now, not *queried*); "Prepare Application" CTA wiring (Phase 8).
- **Workflow:** TDD, DRY, YAGNI, commit per green step. Backend from `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run mypy app`, `uv run lint-imports` (uv path: `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`). Frontend from `frontend/`: `pnpm exec vitest run`, `pnpm exec tsc --noEmit`, `pnpm lint` (`pnpm test` hangs — watch mode). DB/Redis-backed tests run in CI.

---

## File Structure

**Backend — new**
| File | Responsibility |
|---|---|
| `backend/alembic/versions/0007_jobs.py` | `jobs` + `job_chunks` tables, indexes, `updated_at` triggers |
| `backend/app/models/job.py` | `Job`, `JobChunk` ORM models |
| `backend/app/domain/jobs/__init__.py` | empty package marker |
| `backend/app/domain/jobs/extractor.py` | `JobExtraction` / `JDSkill` Pydantic models + `JobExtractor` (one LLM call) |
| `backend/app/domain/jobs/ingestor.py` | `JobIngestor.clean(raw_text) -> str` — boilerplate strip, whitespace collapse, length cap |
| `backend/app/domain/jobs/chunking.py` | `chunk_job(extraction) -> list[JobChunkDraft]` — section-aware, token-capped |
| `backend/app/domain/jobs/service.py` | `JobService` — create / get / list_ / update / delete / apply_ingestion |
| `backend/app/domain/jobs/jobs.demo.json` | ~40 pre-structured demo job rows |
| `backend/app/worker/tasks/jobs.py` | `ingest_job` ARQ task + verbatim `_session_for` |
| `backend/app/api/v1/schemas/jobs.py` | `JobCreateIn`, `JobCardOut`, `JobDetailOut`, `JobPatchIn`, `JobListOut` |
| `backend/app/api/v1/jobs.py` | `/jobs` router |

**Backend — modified**
| File | Change |
|---|---|
| `backend/app/models/__init__.py` | `from app.models import job as job` (between `audit` and `auth`… alpha order: after `job`? put after `auth`, before `profile`) |
| `backend/app/core/events.py` | add `def job_channel(job_id: str) -> str` |
| `backend/app/worker/tasks/__init__.py` | export `ingest_job` |
| `backend/app/worker/main.py` | register `ingest_job` in `WorkerSettings.functions` |
| `backend/app/api/v1/router.py` | `api_router.include_router(jobs.router)` |
| `backend/app/seed.py` | `load_jobs_demo()`, `seed_jobs(session=None)`, CLI dispatch for `jobs` and `all` |
| `backend/tests/conftest.py` | extend `_no_enqueue` to also patch `app.domain.jobs.service.enqueue` |

**Frontend — new**
| File | Responsibility |
|---|---|
| `frontend/hooks/useJobEvents.ts` | SSE hook for a job's ingestion status (mirrors `useResumeEvents`) |
| `frontend/components/jobs/JobCard.tsx` | one posting in the Discovery grid |
| `frontend/components/jobs/JobFilters.tsx` | search box + filter controls, all bound to URL search params |
| `frontend/components/jobs/AddJobDialog.tsx` | paste-a-JD textarea → create → watch status → navigate |
| `frontend/app/(app)/jobs/page.tsx` | Discovery page |
| `frontend/app/(app)/jobs/[id]/page.tsx` | Job Detail page |

**Frontend — modified**
| File | Change |
|---|---|
| `frontend/lib/api/types.ts` | `JobCard`, `JobDetail`, `JobSkillRef`, `JobListResponse`, `JobFilters` types |
| `frontend/lib/api/endpoints.ts` | `api.jobs` group |
| `frontend/lib/query.ts` | `qk.jobs`, `qk.jobsList`, `qk.job` |
| `frontend/components/layout/nav-items.ts` | flip `/jobs` nav item to `ready: true` |

---

## Task 1: `jobs` + `job_chunks` schema

**Files:**
- Create: `backend/alembic/versions/0007_jobs.py`
- Create: `backend/app/models/job.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/test_job_model.py`

**Interfaces — Produces:**
- `Job(Base, TimestampMixin)` — `__tablename__ = "jobs"`. Columns: `id: Mapped[uuid.UUID]`; `user_id: Mapped[uuid.UUID | None]` (FK `users.id` ondelete CASCADE, nullable); `is_seed: Mapped[bool]` (default false); `source: Mapped[str]` (String(20), default `'user_paste'`, CHECK `source in ('user_paste','user_upload','seed')`); `source_ref: Mapped[str | None]` (String(300)); `raw_text: Mapped[str]` (Text, not null); `title/company/company_domain/location: Mapped[str | None]`; `work_mode: Mapped[str | None]` (String(16), CHECK `work_mode in ('remote','hybrid','onsite')`); `employment_type: Mapped[str | None]` (String(40)); `seniority: Mapped[str | None]` (String(20), CHECK `seniority in ('intern','junior','mid','senior','staff','principal','lead','manager')`); `experience_min_years/experience_max_years/salary_min/salary_max: Mapped[int | None]`; `salary_currency: Mapped[str | None]` (String(3)); `salary_period: Mapped[str | None]` (String(10), CHECK `salary_period in ('year','month','day','hour')`); `salary_source: Mapped[str | None]` (String(16), CHECK `salary_source in ('jd','estimate')`); `description: Mapped[str | None]` (Text); `responsibilities: Mapped[list[str]]` (`ARRAY(Text)`, server_default `'{}'`); `required_skills / preferred_skills: Mapped[list[dict[str, Any]]]` (`JSONB`, server_default `'[]'::jsonb`); `structured / extraction_meta: Mapped[dict[str, Any]]` (`JSONB`, server_default `'{}'::jsonb`); `status: Mapped[str]` (String(16), default `'ingesting'`, CHECK `status in ('ingesting','ready','failed')`); `ingest_error: Mapped[str | None]` (Text); `posted_at / deleted_at: Mapped[dt.datetime | None]`; `search_tsv: Mapped[str]` (`TSVECTOR`, `Computed(<expr>, persisted=True)`).
- `JobChunk(Base, TimestampMixin)` — `__tablename__ = "job_chunks"`. Columns: `id`; `job_id: Mapped[uuid.UUID]` (FK `jobs.id` ondelete CASCADE, not null); `owner_id: Mapped[uuid.UUID | None]`; `chunk_index: Mapped[int]`; `section: Mapped[str]` (String(20), CHECK `section in ('description','responsibilities','requirements')`); `content: Mapped[str]` (Text); `token_count: Mapped[int]`; `embed_model: Mapped[str]` (String(60)); `embed_dim: Mapped[int]`; `embedding: Mapped[list[float] | None]` (`Vector(1024)`); `chunk_tsv: Mapped[str]` (`TSVECTOR`, `Computed("to_tsvector('english', content)", persisted=True)`). `UniqueConstraint("job_id", "chunk_index", name="uq_job_chunks_job_chunk")`.
- Migration `revision = "0007_jobs"`, `down_revision = "0006_skills"`.

- [ ] **Step 1: Write the failing model test**

`backend/tests/models/test_job_model.py`:

```python
import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.job import Job, JobChunk
from app.models.user import User


async def _user(db_session, email="job@example.com"):
    u = User(email=email, password_hash="x", full_name="J")
    db_session.add(u)
    await db_session.flush()
    return u


async def test_job_defaults_and_seed_row_has_null_user(db_session):
    job = Job(raw_text="We are hiring an ML Engineer.", is_seed=True, source="seed",
              title="ML Engineer", company="Acme", status="ready")
    db_session.add(job)
    await db_session.flush()
    got = (await db_session.execute(select(Job).where(Job.id == job.id))).scalar_one()
    assert got.user_id is None
    assert got.responsibilities == []
    assert got.required_skills == [] and got.preferred_skills == []
    assert got.structured == {} and got.extraction_meta == {}
    assert got.status == "ready"


async def test_job_status_check_rejects_bad_value(db_session):
    u = await _user(db_session)
    job = Job(user_id=u.id, raw_text="x", status="bogus")
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_search_tsv_is_generated_from_title_company_description(db_session):
    job = Job(raw_text="x", title="Senior Rust Engineer", company="Foobar",
              description="Build low-latency services.", status="ready")
    db_session.add(job)
    await db_session.flush()
    await db_session.refresh(job)
    row = (await db_session.execute(
        select(Job).where(Job.search_tsv.op("@@")(  # websearch match
            __import__("sqlalchemy").func.websearch_to_tsquery("english", "rust")))
    )).scalar_one()
    assert row.id == job.id


async def test_job_chunk_unique_index_and_cascade(db_session):
    job = Job(raw_text="x", status="ready")
    db_session.add(job)
    await db_session.flush()
    db_session.add(JobChunk(job_id=job.id, chunk_index=0, section="description",
                            content="c", token_count=1, embed_model="fake-embed-1", embed_dim=1024))
    await db_session.flush()
    db_session.add(JobChunk(job_id=job.id, chunk_index=0, section="description",
                            content="d", token_count=1, embed_model="fake-embed-1", embed_dim=1024))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 2: Run it — expect collection/import failure**

Run: `"$UV" run pytest tests/models/test_job_model.py -q`
Expected: FAIL — `ModuleNotFoundError: app.models.job`.

- [ ] **Step 3: Write `backend/app/models/job.py`**

```python
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_TSV_EXPR = (
    "to_tsvector('english', "
    "coalesce(title,'') || ' ' || coalesce(company,'') || ' ' || "
    "coalesce(description,'') || ' ' || array_to_string(responsibilities, ' '))"
)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("source in ('user_paste','user_upload','seed')", name="jobs_source_valid"),
        CheckConstraint(
            "work_mode is null or work_mode in ('remote','hybrid','onsite')",
            name="jobs_work_mode_valid",
        ),
        CheckConstraint(
            "seniority is null or seniority in "
            "('intern','junior','mid','senior','staff','principal','lead','manager')",
            name="jobs_seniority_valid",
        ),
        CheckConstraint(
            "salary_period is null or salary_period in ('year','month','day','hour')",
            name="jobs_salary_period_valid",
        ),
        CheckConstraint(
            "salary_source is null or salary_source in ('jd','estimate')",
            name="jobs_salary_source_valid",
        ),
        CheckConstraint("status in ('ingesting','ready','failed')", name="jobs_status_valid"),
        Index("ix_jobs_user_id", "user_id"),
        Index("ix_jobs_is_seed", "is_seed"),
        Index("ix_jobs_seniority", "seniority"),
        Index("ix_jobs_work_mode", "work_mode"),
        Index("ix_jobs_created_at", text("created_at DESC")),
        Index("ix_jobs_structured", "structured", postgresql_using="gin"),
        Index("ix_jobs_required_skills", "required_skills", postgresql_using="gin",
              postgresql_ops={"required_skills": "jsonb_path_ops"}),
        Index("ix_jobs_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_jobs_title_trgm", "title", postgresql_using="gin",
              postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_jobs_company_trgm", "company", postgresql_using="gin",
              postgresql_ops={"company": "gin_trgm_ops"}),
        # Stable upsert key for the seed loader (Task 7): one seed row per source_ref.
        Index("uq_jobs_seed_source_ref", "source_ref", unique=True,
              postgresql_where=text("is_seed")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    is_seed: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'user_paste'"))
    source_ref: Mapped[str | None] = mapped_column(String(300))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200))
    company_domain: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    work_mode: Mapped[str | None] = mapped_column(String(16))
    employment_type: Mapped[str | None] = mapped_column(String(40))
    seniority: Mapped[str | None] = mapped_column(String(20))
    experience_min_years: Mapped[int | None] = mapped_column(Integer)
    experience_max_years: Mapped[int | None] = mapped_column(Integer)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(10))
    salary_source: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    required_skills: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    preferred_skills: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    structured: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    extraction_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'ingesting'"))
    ingest_error: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[dt.datetime | None] = mapped_column()
    deleted_at: Mapped[dt.datetime | None] = mapped_column()
    # Read-only: Postgres maintains this from title/company/description/responsibilities.
    search_tsv: Mapped[str] = mapped_column(TSVECTOR, Computed(_TSV_EXPR, persisted=True))


class JobChunk(Base, TimestampMixin):
    __tablename__ = "job_chunks"
    __table_args__ = (
        UniqueConstraint("job_id", "chunk_index", name="uq_job_chunks_job_chunk"),
        CheckConstraint(
            "section in ('description','responsibilities','requirements')",
            name="job_chunks_section_valid",
        ),
        Index("ix_job_chunks_job_id", "job_id"),
        Index("ix_job_chunks_chunk_tsv", "chunk_tsv", postgresql_using="gin"),
        Index(
            "ix_job_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embed_model: Mapped[str] = mapped_column(String(60), nullable=False)
    embed_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    # The literal dim must stay in sync with app/core/config.py `embed_dim` and the migration.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    chunk_tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
```

- [ ] **Step 4: Write `backend/alembic/versions/0007_jobs.py`**

Model the file on `0006_skills.py`. Use `pg.TSVECTOR`, `Vector`, `sa.Computed(_TSV_EXPR, persisted=True)`. Full `upgrade()`:

```python
"""jobs + job_chunks tables

Revision ID: 0007_jobs
Revises: 0006_skills
Create Date: 2026-09-02
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0007_jobs"
down_revision = "0006_skills"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")
_TSV_EXPR = (
    "to_tsvector('english', "
    "coalesce(title,'') || ' ' || coalesce(company,'') || ' ' || "
    "coalesce(description,'') || ' ' || array_to_string(responsibilities, ' '))"
)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("is_seed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'user_paste'")),
        sa.Column("source_ref", sa.String(300)),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("title", sa.String(300)),
        sa.Column("company", sa.String(200)),
        sa.Column("company_domain", sa.String(200)),
        sa.Column("location", sa.String(200)),
        sa.Column("work_mode", sa.String(16)),
        sa.Column("employment_type", sa.String(40)),
        sa.Column("seniority", sa.String(20)),
        sa.Column("experience_min_years", sa.Integer),
        sa.Column("experience_max_years", sa.Integer),
        sa.Column("salary_min", sa.Integer),
        sa.Column("salary_max", sa.Integer),
        sa.Column("salary_currency", sa.String(3)),
        sa.Column("salary_period", sa.String(10)),
        sa.Column("salary_source", sa.String(16)),
        sa.Column("description", sa.Text),
        sa.Column("responsibilities", sa.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("required_skills", pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("preferred_skills", pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("structured", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("extraction_meta", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'ingesting'")),
        sa.Column("ingest_error", sa.Text),
        sa.Column("posted_at", _TS),
        sa.Column("deleted_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("search_tsv", pg.TSVECTOR, sa.Computed(_TSV_EXPR, persisted=True)),
        sa.CheckConstraint("source in ('user_paste','user_upload','seed')", name="jobs_source_valid"),
        sa.CheckConstraint("work_mode is null or work_mode in ('remote','hybrid','onsite')",
                           name="jobs_work_mode_valid"),
        sa.CheckConstraint(
            "seniority is null or seniority in "
            "('intern','junior','mid','senior','staff','principal','lead','manager')",
            name="jobs_seniority_valid"),
        sa.CheckConstraint("salary_period is null or salary_period in ('year','month','day','hour')",
                           name="jobs_salary_period_valid"),
        sa.CheckConstraint("salary_source is null or salary_source in ('jd','estimate')",
                           name="jobs_salary_source_valid"),
        sa.CheckConstraint("status in ('ingesting','ready','failed')", name="jobs_status_valid"),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_is_seed", "jobs", ["is_seed"])
    op.create_index("ix_jobs_seniority", "jobs", ["seniority"])
    op.create_index("ix_jobs_work_mode", "jobs", ["work_mode"])
    op.create_index("ix_jobs_created_at", "jobs", [sa.text("created_at DESC")])
    op.create_index("ix_jobs_structured", "jobs", ["structured"], postgresql_using="gin")
    op.create_index("ix_jobs_required_skills", "jobs", ["required_skills"],
                    postgresql_using="gin", postgresql_ops={"required_skills": "jsonb_path_ops"})
    op.create_index("ix_jobs_search_tsv", "jobs", ["search_tsv"], postgresql_using="gin")
    op.create_index("ix_jobs_title_trgm", "jobs", ["title"],
                    postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"})
    op.create_index("ix_jobs_company_trgm", "jobs", ["company"],
                    postgresql_using="gin", postgresql_ops={"company": "gin_trgm_ops"})
    op.create_index("uq_jobs_seed_source_ref", "jobs", ["source_ref"], unique=True,
                    postgresql_where=sa.text("is_seed"))
    op.execute("CREATE TRIGGER trg_jobs_set_updated_at BEFORE UPDATE ON jobs "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "job_chunks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True)),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("section", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("embed_model", sa.String(60), nullable=False),
        sa.Column("embed_dim", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("chunk_tsv", pg.TSVECTOR,
                  sa.Computed("to_tsvector('english', content)", persisted=True)),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.UniqueConstraint("job_id", "chunk_index", name="uq_job_chunks_job_chunk"),
        sa.CheckConstraint("section in ('description','responsibilities','requirements')",
                           name="job_chunks_section_valid"),
    )
    op.create_index("ix_job_chunks_job_id", "job_chunks", ["job_id"])
    op.create_index("ix_job_chunks_chunk_tsv", "job_chunks", ["chunk_tsv"], postgresql_using="gin")
    op.create_index("ix_job_chunks_embedding", "job_chunks", ["embedding"],
                    postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64},
                    postgresql_ops={"embedding": "vector_cosine_ops"})
    op.execute("CREATE TRIGGER trg_job_chunks_set_updated_at BEFORE UPDATE ON job_chunks "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_job_chunks_set_updated_at ON job_chunks")
    op.drop_table("job_chunks")
    op.execute("DROP TRIGGER IF EXISTS trg_jobs_set_updated_at ON jobs")
    op.drop_table("jobs")
```

- [ ] **Step 5: Register the model** — in `backend/app/models/__init__.py` add `from app.models import job as job` (keep the file's existing alpha ordering — it goes after `from app.models import audit ... auth` and before `profile`).

- [ ] **Step 6: Run gates**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest tests/models/test_job_model.py -q`
Expected: ruff/mypy/lint-imports clean; the 4 model tests PASS (they need Postgres — pass locally if a DB is available, otherwise `--collect-only` must be error-free and the tests verify in CI).

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/0007_jobs.py backend/app/models/job.py backend/app/models/__init__.py backend/tests/models/test_job_model.py
git commit -m "feat(jobs): jobs + job_chunks tables (migration 0007)"
```

---

## Task 2: `JobExtraction` schema + `JobExtractor`

**Files:**
- Create: `backend/app/domain/jobs/__init__.py` (empty)
- Create: `backend/app/domain/jobs/extractor.py`
- Test: `backend/tests/domain/jobs/test_extractor.py`

**Interfaces:**
- Consumes: `app.domain.llm.provider.{LLMProvider, LLMMessage, LLMResult}`; `app.core.errors.AppError`.
- Produces:
  - `class JDSkill(BaseModel)` — `raw: str`, `weight: float = 0.5`.
  - `class JobExtraction(BaseModel)` — `model_config = ConfigDict(extra="ignore")`; fields: `title, company, company_domain, location, work_mode, employment_type, seniority: str | None = None`; `experience_min_years, experience_max_years, salary_min, salary_max: int | None = None`; `salary_currency, salary_period: str | None = None`; `description: str | None = None`; `responsibilities: list[str] = Field(default_factory=list)`; `required_skills, preferred_skills: list[JDSkill] = Field(default_factory=list)`.
  - `class JobExtractor` — `__init__(self, llm: LLMProvider, *, model: str)`; `last_usage: LLMResult | None`; `async def extract(self, text: str) -> JobExtraction` — one `llm.complete(messages, schema=JobExtraction, max_tokens=4096)` call; raises `AppError(code="job.extraction_failed")` when `result.structured is None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/jobs/test_extractor.py` (no DB — mirrors `tests/domain/resume/test_extractor.py`):

```python
import json

import pytest

from app.core.errors import AppError
from app.domain.jobs.extractor import JDSkill, JobExtraction, JobExtractor
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMResult


async def test_extract_returns_empty_model_from_fake_provider():
    out = await JobExtractor(FakeLLMProvider(), model="fake").extract(
        "Senior ML Engineer at Acme. Remote. Python, PyTorch. $180k-$220k."
    )
    assert isinstance(out, JobExtraction)
    assert out.title is None and out.responsibilities == []
    assert out.required_skills == [] and out.preferred_skills == []


async def test_extract_validates_a_real_structured_payload():
    payload = JobExtraction(
        title="Senior ML Engineer", company="Acme", work_mode="remote",
        seniority="senior", salary_min=180000, salary_max=220000, salary_currency="USD",
        salary_period="year", responsibilities=["Ship models", "Mentor"],
        required_skills=[JDSkill(raw="Python", weight=0.9), JDSkill(raw="PyTorch", weight=0.8)],
        preferred_skills=[JDSkill(raw="Kubernetes", weight=0.4)],
    ).model_dump()

    class _Canned(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            base = await super().complete(messages, schema=None, max_tokens=max_tokens)
            return LLMResult(text=json.dumps(payload), model=base.model,
                             input_tokens=base.input_tokens, output_tokens=base.output_tokens,
                             cost_usd=0.0, structured=payload)

    out = await JobExtractor(_Canned(), model="fake").extract("...")
    assert out.title == "Senior ML Engineer"
    assert [s.raw for s in out.required_skills] == ["Python", "PyTorch"]
    assert out.preferred_skills[0].weight == 0.4


async def test_extract_raises_when_no_structured():
    class _NoStructured(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            return await super().complete(messages, schema=None, max_tokens=max_tokens)

    with pytest.raises(AppError):
        await JobExtractor(_NoStructured(), model="fake").extract("x")
```

- [ ] **Step 2: Run — expect import failure.** `"$UV" run pytest tests/domain/jobs/test_extractor.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/app/domain/jobs/extractor.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import AppError
from app.domain.llm.provider import LLMMessage, LLMProvider, LLMResult


class JDSkill(BaseModel):
    raw: str
    weight: float = 0.5


class JobExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    company: str | None = None
    company_domain: str | None = None
    location: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    description: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[JDSkill] = Field(default_factory=list)
    preferred_skills: list[JDSkill] = Field(default_factory=list)


EXTRACTION_SYSTEM_PROMPT = (
    "Extract structured facts from the job description. Return only what the "
    "text states; never infer. Use null for absent optional fields and empty "
    "lists for absent arrays. Always include every field. work_mode must be one "
    "of remote|hybrid|onsite or null. seniority must be one of "
    "intern|junior|mid|senior|staff|principal|lead|manager or null. "
    "salary_period must be one of year|month|day|hour or null. For "
    "required_skills and preferred_skills, give each skill a `raw` name as "
    "written and a `weight` from 0 to 1 for how central it is to the role."
)


class JobExtractor:
    def __init__(self, llm: LLMProvider, *, model: str) -> None:
        self._llm = llm
        self._model = model
        self.last_usage: LLMResult | None = None

    async def extract(self, text: str) -> JobExtraction:
        messages: list[LLMMessage] = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": text[:20000]},
        ]
        result = await self._llm.complete(messages, schema=JobExtraction, max_tokens=4096)
        self.last_usage = result
        if result.structured is None:
            raise AppError(code="job.extraction_failed")
        return JobExtraction.model_validate(result.structured)
```

- [ ] **Step 4: Run** `"$UV" run pytest tests/domain/jobs/test_extractor.py -q` → 3 PASS. Then `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports` → clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/jobs/__init__.py backend/app/domain/jobs/extractor.py backend/tests/domain/jobs/test_extractor.py
git commit -m "feat(jobs): JobExtraction schema + JobExtractor"
```

---

## Task 3: `JobIngestor` (clean) + `chunk_job` chunker

**Files:**
- Create: `backend/app/domain/jobs/ingestor.py`
- Create: `backend/app/domain/jobs/chunking.py`
- Test: `backend/tests/domain/jobs/test_ingestor.py`
- Test: `backend/tests/domain/jobs/test_chunking.py`

**Interfaces:**
- Consumes: `app.domain.jobs.extractor.JobExtraction`.
- Produces:
  - `ingestor.py`: `MAX_RAW_CHARS = 40_000`; `class JobIngestor` with `def clean(self, raw_text: str) -> str` — normalise newlines, collapse 3+ blank lines to one, strip trailing spaces per line, `strip()`, truncate to `MAX_RAW_CHARS`. Raises `ValidationAppError(code="job.empty")` when the cleaned text is `< 40` chars.
  - `chunking.py`: `@dataclass(frozen=True) class JobChunkDraft` — `section: str` (`"description" | "responsibilities" | "requirements"`), `chunk_index: int`, `content: str`, `token_count: int`. `def chunk_job(extraction: JobExtraction, *, max_tokens: int = 350, overlap: int = 40) -> list[JobChunkDraft]` — builds section texts (`description` = `extraction.description or ""`; `responsibilities` = `"\n".join("- " + r for r in extraction.responsibilities)`; `requirements` = lines `"Required: <raw> (<weight>)"` / `"Preferred: <raw> (<weight>)"`), drops empty sections, splits any section whose whitespace-token count exceeds `max_tokens` into overlapping windows, assigns a global running `chunk_index` starting at 0. `def estimate_tokens(text: str) -> int` = `len(text.split())`.

- [ ] **Step 1: Write failing tests**

`backend/tests/domain/jobs/test_ingestor.py`:

```python
import pytest

from app.core.errors import ValidationAppError
from app.domain.jobs.ingestor import JobIngestor


def test_clean_collapses_blank_lines_and_trims():
    raw = "  Senior ML Engineer  \n\n\n\n  Build models.  \n\n\n"
    out = JobIngestor().clean(raw)
    assert out == "Senior ML Engineer\n\nBuild models."


def test_clean_truncates_to_cap():
    out = JobIngestor().clean("x " * 30_000)
    assert len(out) <= 40_000


def test_clean_rejects_near_empty():
    with pytest.raises(ValidationAppError):
        JobIngestor().clean("   hi   ")
```

`backend/tests/domain/jobs/test_chunking.py`:

```python
from app.domain.jobs.chunking import chunk_job, estimate_tokens
from app.domain.jobs.extractor import JDSkill, JobExtraction


def test_chunk_job_emits_one_chunk_per_nonempty_section_with_running_index():
    ex = JobExtraction(
        description="We build low-latency inference services.",
        responsibilities=["Own the serving stack", "Mentor two engineers"],
        required_skills=[JDSkill(raw="Python", weight=0.9)],
        preferred_skills=[JDSkill(raw="Rust", weight=0.3)],
    )
    chunks = chunk_job(ex)
    sections = [c.section for c in chunks]
    assert sections == ["description", "responsibilities", "requirements"]
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert "Own the serving stack" in chunks[1].content
    assert "Required: Python" in chunks[2].content and "Preferred: Rust" in chunks[2].content
    assert all(c.token_count == estimate_tokens(c.content) for c in chunks)


def test_chunk_job_splits_a_long_section_with_overlap():
    long_desc = " ".join(f"w{i}" for i in range(900))
    chunks = chunk_job(JobExtraction(description=long_desc), max_tokens=300, overlap=40)
    desc_chunks = [c for c in chunks if c.section == "description"]
    assert len(desc_chunks) >= 3
    assert all(c.token_count <= 300 for c in desc_chunks)
    # consecutive windows overlap
    first_tail = desc_chunks[0].content.split()[-40:]
    assert any(w in desc_chunks[1].content.split()[:60] for w in first_tail)


def test_chunk_job_skips_empty_sections():
    chunks = chunk_job(JobExtraction(responsibilities=["Only this"]))
    assert [c.section for c in chunks] == ["responsibilities"]
    assert chunks[0].chunk_index == 0
```

- [ ] **Step 2: Run — expect import failure.**

- [ ] **Step 3: Implement `ingestor.py`**

```python
from __future__ import annotations

import re

from app.core.errors import ValidationAppError

MAX_RAW_CHARS = 40_000
_MIN_MEANINGFUL = 40
_BLANK_RUN = re.compile(r"\n[ \t]*\n[ \t]*\n+")
_TRAIL_WS = re.compile(r"[ \t]+\n")


class JobIngestor:
    def clean(self, raw_text: str) -> str:
        s = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        s = _TRAIL_WS.sub("\n", s)
        s = _BLANK_RUN.sub("\n\n", s)
        s = s.strip()[:MAX_RAW_CHARS].strip()
        if len(s) < _MIN_MEANINGFUL:
            raise ValidationAppError(code="job.empty")
        return s
```

- [ ] **Step 4: Implement `chunking.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from app.domain.jobs.extractor import JobExtraction

_SECTIONS = ("description", "responsibilities", "requirements")


@dataclass(frozen=True)
class JobChunkDraft:
    section: str
    chunk_index: int
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    return len(text.split())


def _section_text(extraction: JobExtraction, section: str) -> str:
    if section == "description":
        return (extraction.description or "").strip()
    if section == "responsibilities":
        return "\n".join(f"- {r}" for r in extraction.responsibilities if r.strip()).strip()
    lines = [f"Required: {s.raw} ({s.weight:.2f})" for s in extraction.required_skills]
    lines += [f"Preferred: {s.raw} ({s.weight:.2f})" for s in extraction.preferred_skills]
    return "\n".join(lines).strip()


def _windows(text: str, *, max_tokens: int, overlap: int) -> list[str]:
    words = text.split()
    if len(words) <= max_tokens:
        return [text] if text else []
    step = max(1, max_tokens - overlap)
    return [" ".join(words[i : i + max_tokens]) for i in range(0, len(words), step)]


def chunk_job(
    extraction: JobExtraction, *, max_tokens: int = 350, overlap: int = 40
) -> list[JobChunkDraft]:
    drafts: list[JobChunkDraft] = []
    idx = 0
    for section in _SECTIONS:
        text = _section_text(extraction, section)
        if not text:
            continue
        for window in _windows(text, max_tokens=max_tokens, overlap=overlap):
            drafts.append(
                JobChunkDraft(
                    section=section,
                    chunk_index=idx,
                    content=window,
                    token_count=estimate_tokens(window),
                )
            )
            idx += 1
    return drafts
```

- [ ] **Step 5: Run** both test files → all PASS. `ruff` / `mypy` / `lint-imports` → clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/jobs/ingestor.py backend/app/domain/jobs/chunking.py backend/tests/domain/jobs/test_ingestor.py backend/tests/domain/jobs/test_chunking.py
git commit -m "feat(jobs): JobIngestor text cleaner + section-aware chunker"
```

---

## Task 4: `JobService`

**Files:**
- Create: `backend/app/domain/jobs/service.py`
- Modify: `backend/tests/conftest.py` (extend `_no_enqueue`)
- Test: `backend/tests/domain/jobs/test_service.py`

**Interfaces:**
- Consumes: `Job`, `JobChunk` (Task 1); `JobExtraction` (Task 2); `JobChunkDraft` (Task 3); `SkillNormalizer` + `SkillMatch` (`app.domain.skills.normalizer`); `get_embeddings_provider` (`app.domain.embeddings.factory`); `audit` (`app.core.audit`); `enqueue` (`app.core.queue`); `NotFoundError`, `ForbiddenError`, `ValidationAppError` (`app.core.errors`); `current_request_id` (`app.core.logging`).
- Produces — `class JobService`:
  - `__init__(self, session: AsyncSession, *, settings: Settings | None = None)`.
  - `@dataclass(frozen=True) class JobFilters` — `q: str | None = None`, `work_mode: str | None = None`, `seniority: str | None = None`, `location: str | None = None`, `salary_min: int | None = None`, `employment_type: str | None = None`, `skills: tuple[str, ...] = ()` (slug csv), `sort: str = "recent"`, `limit: int = 24`, `offset: int = 0`.
  - `async def create(self, user_id: uuid.UUID, *, raw_text: str) -> Job` — `raw_text.strip()` must be `>= 40` chars else `ValidationAppError(code="job.empty")`; insert `Job(user_id=user_id, raw_text=<stripped>, source="user_paste", status="ingesting")`; `flush`; `await enqueue("ingest_job", str(job.id), _defer_by=2.0, _job_id=f"ingest_job:{job.id}")`; audit `action="job.create"`, `resource_type="job"`, `resource_id=job.id`; return job.
  - `async def get(self, user_id: uuid.UUID, job_id: uuid.UUID) -> Job` — `select(Job).where(Job.id == job_id, Job.deleted_at.is_(None), or_(Job.user_id == user_id, Job.user_id.is_(None)))`; `NotFoundError(detail="Job not found")` if none.
  - `async def list_(self, user_id: uuid.UUID, filters: JobFilters) -> tuple[list[Job], int]` — base `where` `(Job.user_id == user_id) | Job.user_id.is_(None)` + `Job.deleted_at.is_(None)` + `Job.status == "ready"`; `q` → `Job.search_tsv.op("@@")(func.websearch_to_tsquery("english", q)) | Job.title.ilike(f"%{q}%") | Job.company.ilike(f"%{q}%")`; `work_mode`/`seniority`/`employment_type` equality; `location` → `Job.location.ilike(f"%{location}%")`; `salary_min` → `Job.salary_max >= salary_min` (a job matches if its top end clears the floor) `| Job.salary_max.is_(None)`; `skills` → for every slug `Job.required_skills.op("@>")(cast([{"slug": slug}], JSONB))` AND-ed; `sort`: `"recent"` (default and the `"match"` fallback) → `order_by(Job.created_at.desc())`; total via `select(func.count()).select_from(<subquery of filtered ids>)`; page with `.limit(filters.limit).offset(filters.offset)`.
  - `async def update(self, user_id: uuid.UUID, job_id: uuid.UUID, *, title: str | None) -> Job` — load via `_owned` (`Job.user_id == user_id` **exactly** — seed rows excluded); `NotFoundError` if none (a seed job id returns 404 here, not 403 — do not reveal it as editable). `title` clamped to 300, then `flush`, return. (Only `title` is patchable in Phase 4 — YAGNI.)
  - `async def delete(self, user_id: uuid.UUID, job_id: uuid.UUID) -> None` — load with `Job.user_id == user_id` exactly; `NotFoundError` if none; set `deleted_at = dt.datetime.now(dt.UTC)`; `flush`; audit `action="job.delete"`.
  - `async def apply_ingestion(self, job_id: uuid.UUID, *, extraction: JobExtraction, required: list[dict], preferred: list[dict], chunks: list[tuple[JobChunkDraft, list[float]]], meta: dict) -> None` — worker callback: load job (any owner), write every scalar column from `extraction` (clamp `title` 300 / `company` 200 / `location` 200 / `company_domain` 200), `responsibilities = list(extraction.responsibilities)`, `required_skills = required`, `preferred_skills = preferred`, `structured = extraction.model_dump()`, `extraction_meta = meta`, `status = "ready"`, `ingest_error = None`; `DELETE FROM job_chunks WHERE job_id = :job_id`; insert a `JobChunk` per `(draft, vec)` with `owner_id = job.user_id`, `embed_model = provider.model`… — wait, the provider isn't here; take `embed_model`/`embed_dim` from `meta["embed_model"]`/`meta["embed_dim"]` which the worker fills; `flush`.

- [ ] **Step 1: Extend the conftest enqueue guard**

In `backend/tests/conftest.py`, the `_no_enqueue` autouse fixture currently patches only `app.domain.resume.service.enqueue`. Add a second line so job creation in tests never reaches Redis:

```python
    monkeypatch.setattr("app.domain.jobs.service.enqueue", _noop, raising=False)
```

- [ ] **Step 2: Write the failing service test**

`backend/tests/domain/jobs/test_service.py` (DB). Covers: `create` inserts `status="ingesting"` + enqueues (assert via a locally-patched spy); `get` returns own + seed rows and 404s a cross-user row; `list_` filters by `q` (tsv), `work_mode`, and `skills` slug, honours `limit`/`offset`, and returns the right `total`; `delete` soft-deletes a user row and 404s a seed row.

```python
import uuid

import pytest

from app.domain.jobs.extractor import JobExtraction
from app.domain.jobs.service import JobFilters, JobService
from app.models.job import Job
from app.models.user import User


async def _user(db_session, email):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    return u


def _ready_job(**kw):
    base = dict(raw_text="x" * 60, status="ready", is_seed=False)
    base.update(kw)
    return Job(**base)


async def test_create_inserts_ingesting_and_enqueues(db_session, monkeypatch):
    calls: list[tuple] = []

    async def _spy(task, *a, **k):
        calls.append((task, a, k))
        return "job-1"

    monkeypatch.setattr("app.domain.jobs.service.enqueue", _spy)
    u = await _user(db_session, "c1@x.com")
    job = await JobService(db_session).create(u.id, raw_text="Senior ML Engineer\n" + "detail " * 20)
    assert job.status == "ingesting" and job.source == "user_paste" and job.user_id == u.id
    assert calls and calls[0][0] == "ingest_job"


async def test_create_rejects_near_empty(db_session):
    u = await _user(db_session, "c2@x.com")
    with pytest.raises(Exception):
        await JobService(db_session).create(u.id, raw_text="too short")


async def test_get_returns_own_and_seed_but_not_other_users(db_session):
    u1 = await _user(db_session, "g1@x.com")
    u2 = await _user(db_session, "g2@x.com")
    mine = _ready_job(user_id=u1.id, title="Mine")
    seed = _ready_job(user_id=None, is_seed=True, source="seed", title="Seed")
    theirs = _ready_job(user_id=u2.id, title="Theirs")
    db_session.add_all([mine, seed, theirs])
    await db_session.flush()
    svc = JobService(db_session)
    assert (await svc.get(u1.id, mine.id)).title == "Mine"
    assert (await svc.get(u1.id, seed.id)).title == "Seed"
    with pytest.raises(Exception):
        await svc.get(u1.id, theirs.id)


async def test_list_filters_by_query_workmode_and_skill_slug(db_session):
    u = await _user(db_session, "l1@x.com")
    db_session.add_all([
        _ready_job(user_id=None, is_seed=True, source="seed", title="Rust Platform Engineer",
                   company="Foo", work_mode="remote",
                   required_skills=[{"skill_id": str(uuid.uuid4()), "slug": "rust", "label": "Rust", "weight": 0.9}]),
        _ready_job(user_id=None, is_seed=True, source="seed", title="Frontend Engineer",
                   company="Bar", work_mode="onsite",
                   required_skills=[{"skill_id": str(uuid.uuid4()), "slug": "react", "label": "React", "weight": 0.8}]),
    ])
    await db_session.flush()
    svc = JobService(db_session)
    rows, total = await svc.list_(u.id, JobFilters(q="rust"))
    assert total == 1 and rows[0].title == "Rust Platform Engineer"
    rows, total = await svc.list_(u.id, JobFilters(work_mode="remote"))
    assert {r.title for r in rows} == {"Rust Platform Engineer"}
    rows, total = await svc.list_(u.id, JobFilters(skills=("react",)))
    assert {r.title for r in rows} == {"Frontend Engineer"}


async def test_delete_soft_deletes_user_job_and_404s_seed(db_session):
    u = await _user(db_session, "d1@x.com")
    mine = _ready_job(user_id=u.id, title="Mine")
    seed = _ready_job(user_id=None, is_seed=True, source="seed", title="Seed")
    db_session.add_all([mine, seed])
    await db_session.flush()
    svc = JobService(db_session)
    await svc.delete(u.id, mine.id)
    with pytest.raises(Exception):
        await svc.get(u.id, mine.id)
    with pytest.raises(Exception):
        await svc.delete(u.id, seed.id)
```

- [ ] **Step 3: Implement `backend/app/domain/jobs/service.py`**

Follow the `ResumeService` shape (audit helper, `_audit(action, user_id, resource_id=, meta=)` with `resource_type="job"`). Key query bodies:

```python
from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import current_request_id
from app.core.queue import enqueue
from app.domain.jobs.chunking import JobChunkDraft
from app.domain.jobs.extractor import JobExtraction
from app.models.job import Job, JobChunk

_MIN_RAW = 40
_MAXLEN = {"title": 300, "company": 200, "location": 200, "company_domain": 200}


@dataclass(frozen=True)
class JobFilters:
    q: str | None = None
    work_mode: str | None = None
    seniority: str | None = None
    location: str | None = None
    salary_min: int | None = None
    employment_type: str | None = None
    skills: tuple[str, ...] = ()
    sort: str = "recent"
    limit: int = 24
    offset: int = 0


class JobService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def _audit(self, action: str, user_id: uuid.UUID, *,
                     resource_id: uuid.UUID | None = None, meta: dict[str, Any] | None = None) -> None:
        await audit(self.session, actor_type="user", action=action, actor_user_id=user_id,
                    resource_type="job", resource_id=resource_id,
                    request_id=current_request_id(), meta=meta)

    async def create(self, user_id: uuid.UUID, *, raw_text: str) -> Job:
        cleaned = raw_text.strip()
        if len(cleaned) < _MIN_RAW:
            raise ValidationAppError(code="job.empty")
        job = Job(user_id=user_id, raw_text=cleaned, source="user_paste", status="ingesting")
        self.session.add(job)
        await self.session.flush()
        await enqueue("ingest_job", str(job.id), _defer_by=2.0, _job_id=f"ingest_job:{job.id}")
        await self._audit("job.create", user_id, resource_id=job.id)
        return job

    def _visible(self, user_id: uuid.UUID) -> Any:
        return or_(Job.user_id == user_id, Job.user_id.is_(None))

    async def get(self, user_id: uuid.UUID, job_id: uuid.UUID) -> Job:
        row = (await self.session.execute(
            select(Job).where(Job.id == job_id, Job.deleted_at.is_(None), self._visible(user_id))
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError(detail="Job not found")
        return row

    async def _owned(self, user_id: uuid.UUID, job_id: uuid.UUID) -> Job:
        row = (await self.session.execute(
            select(Job).where(Job.id == job_id, Job.user_id == user_id, Job.deleted_at.is_(None))
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError(detail="Job not found")
        return row

    def _filtered(self, user_id: uuid.UUID, f: JobFilters) -> Select[tuple[Job]]:
        stmt = select(Job).where(
            self._visible(user_id), Job.deleted_at.is_(None), Job.status == "ready"
        )
        if f.q:
            stmt = stmt.where(
                Job.search_tsv.op("@@")(func.websearch_to_tsquery("english", f.q))
                | Job.title.ilike(f"%{f.q}%")
                | Job.company.ilike(f"%{f.q}%")
            )
        if f.work_mode:
            stmt = stmt.where(Job.work_mode == f.work_mode)
        if f.seniority:
            stmt = stmt.where(Job.seniority == f.seniority)
        if f.employment_type:
            stmt = stmt.where(Job.employment_type == f.employment_type)
        if f.location:
            stmt = stmt.where(Job.location.ilike(f"%{f.location}%"))
        if f.salary_min is not None:
            stmt = stmt.where(or_(Job.salary_max >= f.salary_min, Job.salary_max.is_(None)))
        for slug in f.skills:
            stmt = stmt.where(Job.required_skills.op("@>")(cast([{"slug": slug}], JSONB)))
        return stmt

    async def list_(self, user_id: uuid.UUID, f: JobFilters) -> tuple[list[Job], int]:
        stmt = self._filtered(user_id, f)
        total = (await self.session.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            stmt.order_by(Job.created_at.desc()).limit(f.limit).offset(f.offset)
        )).scalars().all()
        return list(rows), int(total)

    async def update(self, user_id: uuid.UUID, job_id: uuid.UUID, *, title: str | None) -> Job:
        job = await self._owned(user_id, job_id)
        if title is not None:
            job.title = title[:_MAXLEN["title"]]
        await self.session.flush()
        return job

    async def delete(self, user_id: uuid.UUID, job_id: uuid.UUID) -> None:
        job = await self._owned(user_id, job_id)
        job.deleted_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        await self._audit("job.delete", user_id, resource_id=job_id)

    async def apply_ingestion(
        self, job_id: uuid.UUID, *, extraction: JobExtraction,
        required: list[dict[str, Any]], preferred: list[dict[str, Any]],
        chunks: Sequence[tuple[JobChunkDraft, list[float]]], meta: dict[str, Any],
    ) -> None:
        job = await self.session.get(Job, job_id)
        if job is None:
            raise NotFoundError(detail="Job not found")
        for col in ("company", "company_domain", "location", "work_mode", "employment_type",
                    "seniority", "experience_min_years", "experience_max_years",
                    "salary_min", "salary_max", "salary_currency", "salary_period", "description"):
            val = getattr(extraction, col)
            if isinstance(val, str) and col in _MAXLEN:
                val = val[: _MAXLEN[col]]
            setattr(job, col, val)
        if extraction.title:
            job.title = extraction.title[:_MAXLEN["title"]]
        job.responsibilities = list(extraction.responsibilities)
        job.required_skills = required
        job.preferred_skills = preferred
        job.structured = extraction.model_dump()
        job.extraction_meta = meta
        job.salary_source = "jd" if (extraction.salary_min or extraction.salary_max) else None
        job.status = "ready"
        job.ingest_error = None
        await self.session.execute(
            JobChunk.__table__.delete().where(JobChunk.job_id == job_id)
        )
        for draft, vec in chunks:
            self.session.add(JobChunk(
                job_id=job_id, owner_id=job.user_id, chunk_index=draft.chunk_index,
                section=draft.section, content=draft.content, token_count=draft.token_count,
                embed_model=meta["embed_model"], embed_dim=meta["embed_dim"], embedding=vec,
            ))
        await self.session.flush()
```

- [ ] **Step 4: Run** `"$UV" run pytest tests/domain/jobs/test_service.py -q` (DB) → PASS (or `--collect-only` clean + CI). `ruff`/`mypy`/`lint-imports` → clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/jobs/service.py backend/tests/conftest.py backend/tests/domain/jobs/test_service.py
git commit -m "feat(jobs): JobService — create/get/list/update/delete + apply_ingestion"
```

---

## Task 5: `ingest_job` worker task

**Files:**
- Modify: `backend/app/core/events.py` (add `job_channel`)
- Create: `backend/app/worker/tasks/jobs.py`
- Modify: `backend/app/worker/tasks/__init__.py`
- Modify: `backend/app/worker/main.py`
- Test: `backend/tests/worker/test_jobs_task.py`

**Interfaces:**
- Consumes: `JobService` + its `apply_ingestion` (Task 4); `JobIngestor` (Task 3); `chunk_job` (Task 3); `JobExtractor` (Task 2); `SkillNormalizer` (`app.domain.skills.normalizer`); `get_llm_provider`, `get_embeddings_provider`; `publish_status`, `job_channel`; `record_failure`; `MAX_TRIES` from `app.worker.tasks.resume`.
- Produces:
  - `app/core/events.py`: `def job_channel(job_id: str) -> str: return f"sse:job:{job_id}"` (next to `resume_channel`).
  - `app/worker/tasks/jobs.py`: `__all__ = ["ingest_job"]`; verbatim `_session_for` copy; `async def ingest_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]`.
  - `worker/tasks/__init__.py`: add `from app.worker.tasks.jobs import ingest_job` and to `__all__`.
  - `worker/main.py`: add `ingest_job` to the `from app.worker.tasks import ...` line and to `WorkerSettings.functions`.

- [ ] **Step 1: Write the failing task test**

`backend/tests/worker/test_jobs_task.py` (DB). Monkeypatches `app.worker.tasks.jobs._session_for` to yield `db_session` (see `tests/worker/test_profile_task.py` for the `_ctx` helper pattern), seeds a `Job(status="ingesting", raw_text=...)`, runs `await ingest_job({}, str(job.id))`, asserts the job is `status="ready"`, has `job_chunks` rows with non-null `embedding`, and `extraction_meta` carries `embed_model`.

```python
import contextlib
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select

from app.models.job import Job, JobChunk


@contextlib.asynccontextmanager
async def _ctx(session):
    yield session


async def test_ingest_job_marks_ready_and_writes_embedded_chunks(db_session, monkeypatch):
    from app.worker.tasks import jobs as jobs_task

    monkeypatch.setattr(jobs_task, "_session_for", lambda: _ctx(db_session))

    job = Job(user_id=None, is_seed=False, source="user_paste", status="ingesting",
              raw_text="Senior ML Engineer at Acme. Remote. Own the model serving stack. "
                       "Requires Python and PyTorch. Nice to have Kubernetes.")
    db_session.add(job)
    await db_session.flush()

    out = await jobs_task.ingest_job({}, str(job.id))
    assert out["status"] == "ready"

    await db_session.refresh(job)
    assert job.status == "ready"
    assert job.extraction_meta.get("embed_model")
    n = (await db_session.execute(
        select(func.count()).select_from(JobChunk).where(JobChunk.job_id == job.id)
    )).scalar_one()
    assert n >= 1
    missing = (await db_session.execute(
        select(func.count()).select_from(JobChunk)
        .where(JobChunk.job_id == job.id, JobChunk.embedding.is_(None))
    )).scalar_one()
    assert missing == 0


async def test_ingest_job_skips_when_not_ingesting(db_session, monkeypatch):
    from app.worker.tasks import jobs as jobs_task

    monkeypatch.setattr(jobs_task, "_session_for", lambda: _ctx(db_session))
    job = Job(user_id=None, source="seed", is_seed=True, status="ready", raw_text="x" * 60)
    db_session.add(job)
    await db_session.flush()
    out = await jobs_task.ingest_job({}, str(job.id))
    assert out["status"] == "skipped"
```

- [ ] **Step 2: Run — expect import failure.**

- [ ] **Step 3: Add `job_channel` to `app/core/events.py`** — directly under `resume_channel`:

```python
def job_channel(job_id: str) -> str:
    return f"sse:job:{job_id}"
```

- [ ] **Step 4: Implement `backend/app/worker/tasks/jobs.py`**

```python
from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.events import job_channel, publish_status
from app.core.logging import get_logger
from app.core.redis import redis_from_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.jobs.chunking import chunk_job
from app.domain.jobs.extractor import JobExtractor
from app.domain.jobs.ingestor import JobIngestor
from app.domain.jobs.service import JobService
from app.domain.llm.factory import get_llm_provider
from app.domain.skills.normalizer import SkillNormalizer
from app.models.job import Job
from app.worker.dead_letter import record_failure
from app.worker.tasks.resume import MAX_TRIES

__all__ = ["ingest_job"]

log = get_logger("worker.ingest_job")


@contextlib.asynccontextmanager
async def _session_for() -> AsyncIterator[AsyncSession]:
    """Verbatim copy of app/worker/tasks/resume.py::_session_for (kept local so
    task modules stay decoupled; the DB test monkeypatches this symbol)."""
    async with AsyncSessionLocal() as session:
        yield session


def _resolve(raw_skills: list[Any], matches: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in raw_skills:
        m = matches.get(s.raw)
        if m is None:
            continue
        out.append({"skill_id": str(m.skill_id), "slug": m.slug, "label": m.label,
                    "weight": round(float(s.weight), 2)})
    return out


async def ingest_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    settings = get_settings()
    redis = redis_from_settings(settings)
    channel = job_channel(job_id)
    jid = uuid.UUID(job_id)

    async with _session_for() as session:
        job = await session.get(Job, jid)
        if job is None:
            await record_failure("ingest_job", args=(job_id,), kwargs={},
                                 error=RuntimeError(f"job {job_id} not found"))
            return {"job_id": job_id, "status": "missing"}
        if job.status != "ingesting":
            return {"job_id": job_id, "status": "skipped"}

        try:
            await publish_status(redis, channel, resource="job", id=job_id,
                                 status="ingesting", message="Reading the posting…")
            cleaned = JobIngestor().clean(job.raw_text)

            extractor = JobExtractor(get_llm_provider(settings),
                                     model=settings.llm_model_extraction)
            extraction = await extractor.extract(cleaned)
            await publish_status(redis, channel, resource="job", id=job_id,
                                 status="ingesting", message="Pulling out the requirements…")

            embeddings = get_embeddings_provider(settings)
            normalizer = SkillNormalizer(session, embeddings)
            await normalizer.load()
            all_raw = [s.raw for s in (*extraction.required_skills, *extraction.preferred_skills)]
            matches = await normalizer.normalize_many(all_raw)
            required = _resolve(extraction.required_skills, matches)
            preferred = _resolve(extraction.preferred_skills, matches)

            drafts = chunk_job(extraction)
            vectors = await embeddings.embed_documents([d.content for d in drafts]) if drafts else []
            meta = {
                "model": extractor.last_usage.model if extractor.last_usage else "unknown",
                "embed_model": embeddings.model,
                "embed_dim": embeddings.dim,
                "chunks": len(drafts),
                "unmatched": sorted({r for r in all_raw if r not in matches}),
            }
            await JobService(session, settings=settings).apply_ingestion(
                jid, extraction=extraction, required=required, preferred=preferred,
                chunks=list(zip(drafts, vectors, strict=True)), meta=meta,
            )
            await session.commit()
            log.info("job_ingested", job_id=job_id, chunks=len(drafts),
                     required=len(required), preferred=len(preferred))
            await publish_status(redis, channel, resource="job", id=job_id,
                                 status="ready", message="Ready")
            return {"job_id": job_id, "status": "ready"}
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise
            job = await session.get(Job, jid)
            if job is not None:
                job.status = "failed"
                job.ingest_error = "We couldn't read this job posting."
                await session.commit()
            with contextlib.suppress(Exception):
                await publish_status(redis, channel, resource="job", id=job_id,
                                     status="failed", message="We couldn't read this job posting.")
            await record_failure("ingest_job", args=(job_id,), kwargs={}, error=exc)
            raise
```

- [ ] **Step 5: Register** — `worker/tasks/__init__.py`:

```python
from app.worker.tasks.jobs import ingest_job
```
add `"ingest_job"` to `__all__`. `worker/main.py`: import `ingest_job` from `app.worker.tasks` and append it to `WorkerSettings.functions`.

- [ ] **Step 6: Run** `"$UV" run pytest tests/worker/test_jobs_task.py -q` (DB) → 2 PASS (or `--collect-only` clean + CI). `ruff`/`mypy`/`lint-imports` → clean. Confirm `lint-imports` still "2 kept" (jobs worker task → jobs domain + skills domain + resume worker for `MAX_TRIES` — all within allowed direction).

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/events.py backend/app/worker/tasks/jobs.py backend/app/worker/tasks/__init__.py backend/app/worker/main.py backend/tests/worker/test_jobs_task.py
git commit -m "feat(jobs): ingest_job worker task — clean/extract/normalize/chunk/embed"
```

---

## Task 6: `/jobs` API routes + schemas

**Files:**
- Create: `backend/app/api/v1/schemas/jobs.py`
- Create: `backend/app/api/v1/jobs.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/api/test_jobs.py`

**Interfaces:**
- Consumes: `JobService`, `JobFilters` (Task 4); `CurrentUser`, `DbDep`, `RedisDep` (`app.api.deps`); `job_channel`, `sse_event`, `status_stream` (`app.core.events`); `AsyncSessionLocal`; `NotFoundError`.
- Produces — `app/api/v1/jobs.py` `router = APIRouter(prefix="/jobs", tags=["jobs"])`:
  - `POST ""` → 202, body `JobCreateIn {raw_text: str}` → `JobService(db).create(user.id, raw_text=body.raw_text)` → `JobRefOut {id, status}`.
  - `GET ""` → `JobListOut {items: list[JobCardOut], total: int, limit: int, offset: int}`. Query params (all optional): `q, work_mode, seniority, location, employment_type: str`; `salary_min: int`; `skills: str` (comma list); `sort: str = "recent"`; `limit: int = 24` (clamp 1..60); `offset: int = 0`. Builds `JobFilters(skills=tuple(s for s in skills.split(",") if s))`.
  - `GET "/{job_id}"` → `JobDetailOut`.
  - `GET "/{job_id}/events"` → `EventSourceResponse` — copy the `resume_events` body from `app/api/v1/resumes.py` verbatim, swapping `resume`→`job`, `resume_channel`→`job_channel`, `ResumeService`→`JobService`, `terminal={"ready", "failed"}`, `resource="job"`.
  - `PATCH "/{job_id}"` → body `JobPatchIn {title: str | None}` → `JobService(db).update(user.id, job_id, title=body.title)` → `JobDetailOut`.
  - `DELETE "/{job_id}"` → 204 → `JobService(db).delete(user.id, job_id)`.
- `schemas/jobs.py`:
  - `JobCreateIn` — `model_config = ConfigDict(extra="forbid")`; `raw_text: str = Field(min_length=40, max_length=40_000)`.
  - `JobPatchIn` — `extra="forbid"`; `title: str | None = Field(default=None, max_length=300)`.
  - `JobRefOut` — `id: uuid.UUID`, `status: str`.
  - `JobSkillOut` — `slug: str`, `label: str`, `weight: float`.
  - `JobCardOut` — `model_config = ConfigDict(from_attributes=True)`; `id, title, company, location, work_mode, seniority, employment_type: ... | None`; `salary_min, salary_max: int | None`; `salary_currency, salary_period: str | None`; `is_seed: bool`; `status: str`; `posted_at: dt.datetime | None`; `created_at: dt.datetime`; `required_skills: list[JobSkillOut]` (via a `@field_validator`/computed from the ORM `required_skills` list-of-dict — simplest: keep `JobCardOut` NOT `from_attributes` for that field; build it in the route: `JobCardOut.model_validate(job)` then set `.required_skills`; OR add a `@computed_field`-free mapper `card_out(job)` helper in the router). Use a router-level `_card(job: Job) -> JobCardOut` mapper — explicit, no validator magic.
  - `JobDetailOut(JobCardOut)` — adds `company_domain: str | None`, `experience_min_years, experience_max_years: int | None`, `description: str | None`, `responsibilities: list[str]`, `preferred_skills: list[JobSkillOut]`, `raw_text: str`.
  - `JobListOut` — `items: list[JobCardOut]`, `total: int`, `limit: int`, `offset: int`.

- [ ] **Step 1: Write the failing API test**

`backend/tests/api/test_jobs.py` (DB + Redis — uses the `client` fixture + an auth helper; look at `tests/api/test_profile_skills.py` for the auth pattern). Covers: `POST /jobs` short text → 422; `POST /jobs` valid → 202 + `{id, status: "ingesting"}`; `GET /jobs` returns seeded ready jobs, honours `?work_mode=` and `?q=`; `GET /jobs/{id}` returns a detail with `raw_text`; `DELETE /jobs/{id}` on a seed job → 404; `GET /jobs` excludes `status="ingesting"` rows.

```python
import uuid

from app.models.job import Job


async def _auth(client, email="jobs-api@x.com"):
    await client.post("/api/v1/auth/register",
                      json={"email": email, "password": "pw12345678", "full_name": "J"})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw12345678"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_post_jobs_rejects_short_text(client):
    h = await _auth(client)
    r = await client.post("/api/v1/jobs", headers=h, json={"raw_text": "too short"})
    assert r.status_code == 422


async def test_post_jobs_accepts_and_returns_202(client):
    h = await _auth(client, "jobs-api2@x.com")
    r = await client.post("/api/v1/jobs", headers=h,
                          json={"raw_text": "Senior ML Engineer at Acme. " + "detail " * 20})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "ingesting" and uuid.UUID(body["id"])


async def test_get_jobs_lists_ready_seed_jobs_with_filters(client, db_session):
    h = await _auth(client, "jobs-api3@x.com")
    db_session.add_all([
        Job(user_id=None, is_seed=True, source="seed", status="ready",
            raw_text="x" * 60, title="Remote Rust Engineer", company="Foo", work_mode="remote"),
        Job(user_id=None, is_seed=True, source="seed", status="ready",
            raw_text="x" * 60, title="Onsite React Engineer", company="Bar", work_mode="onsite"),
        Job(user_id=None, is_seed=True, source="seed", status="ingesting",
            raw_text="x" * 60, title="Hidden", company="Baz"),
    ])
    await db_session.commit()
    r = await client.get("/api/v1/jobs", headers=h)
    titles = {j["title"] for j in r.json()["items"]}
    assert "Remote Rust Engineer" in titles and "Onsite React Engineer" in titles
    assert "Hidden" not in titles
    r = await client.get("/api/v1/jobs?work_mode=remote", headers=h)
    assert {j["title"] for j in r.json()["items"]} == {"Remote Rust Engineer"}
    r = await client.get("/api/v1/jobs?q=react", headers=h)
    assert {j["title"] for j in r.json()["items"]} == {"Onsite React Engineer"}


async def test_delete_seed_job_is_404(client, db_session):
    h = await _auth(client, "jobs-api4@x.com")
    job = Job(user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60, title="S")
    db_session.add(job)
    await db_session.commit()
    r = await client.delete(f"/api/v1/jobs/{job.id}", headers=h)
    assert r.status_code == 404
```

- [ ] **Step 2: Run — expect 404s / import failure.**

- [ ] **Step 3: Implement `schemas/jobs.py` then `jobs.py`** per the Interfaces block. Register in `router.py`: `from app.api.v1 import auth, health, jobs, profile, resumes` and `api_router.include_router(jobs.router)`.

- [ ] **Step 4: Run** `"$UV" run pytest tests/api/test_jobs.py -q` (DB+Redis) → PASS (or `--collect-only` + CI). `ruff`/`mypy`/`lint-imports` → clean. `"$UV" run python -c "from app.main import create_app; import os; os.environ.setdefault('DATABASE_URL','x'); ..."` — skip; instead confirm OpenAPI in Task 12.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/schemas/jobs.py backend/app/api/v1/jobs.py backend/app/api/v1/router.py backend/tests/api/test_jobs.py
git commit -m "feat(jobs): /jobs API — create, discovery list, detail, patch, delete, SSE"
```

---

## Task 7: demo dataset + `seed_jobs`

**Files:**
- Create: `backend/app/domain/jobs/jobs.demo.json`
- Modify: `backend/app/seed.py`
- Test: `backend/tests/domain/jobs/test_seed.py`

**Interfaces:**
- Consumes: `Job`, `JobChunk` (Task 1); `JobExtraction`, `JDSkill` (Task 2); `chunk_job` (Task 3); `Skill` (`app.models.skill`); `get_embeddings_provider`; `AsyncSessionLocal`.
- Produces — in `backend/app/seed.py`:
  - `async def load_jobs_demo() -> list[dict[str, Any]]` — reads `Path(__file__).parent / "domain" / "jobs" / "jobs.demo.json"`.
  - `async def seed_jobs(session: AsyncSession | None = None) -> int` — same `session=None` dual-path shape as `seed_skills`. For each row: upsert a `Job` keyed on `source_ref` (the row's `key`), `is_seed=True`, `user_id=None`, `source="seed"`, `status="ready"`; resolve `required_skill_slugs` / `preferred_skill_slugs` against the `skills` table (`select(Skill.id, Skill.slug, Skill.label).where(Skill.slug.in_(slugs))`) into `[{skill_id, slug, label, weight}]` (weight: `0.8` for required, `0.4` for preferred; drop slugs not in the taxonomy); build a `JobExtraction` from the row for `structured` + for `chunk_job`; delete + re-insert `job_chunks` with embeddings from `get_embeddings_provider(settings).embed_documents(...)`; set `raw_text` to a composed plain-text rendering of the row (title/company line + description + "Responsibilities:" bullets + "Requirements:" list). Return the row count.
  - CLI: extend the `__main__` block to accept `skills`, `jobs`, and `all` (`all` = `seed_skills()` then `seed_jobs()`), keeping the existing usage error.

- `backend/app/domain/jobs/jobs.demo.json` — a JSON array of **~40** objects. Each object:

```json
{
  "key": "ml-eng-nimbus-01",
  "title": "Senior Machine Learning Engineer",
  "company": "Nimbus AI",
  "company_domain": "nimbus.ai",
  "location": "San Francisco, CA",
  "work_mode": "hybrid",
  "employment_type": "Full-time",
  "seniority": "senior",
  "experience_min_years": 5,
  "experience_max_years": 9,
  "salary_min": 190000,
  "salary_max": 240000,
  "salary_currency": "USD",
  "salary_period": "year",
  "posted_at": "2026-08-20",
  "description": "Nimbus AI builds retrieval-augmented assistants for enterprise support teams. You will own the model-serving stack end to end — latency budgets, evaluation harnesses, and the feedback loop that turns production traffic into training data.",
  "responsibilities": [
    "Design and operate low-latency inference services for LLM and embedding workloads",
    "Build offline and online evaluation pipelines for retrieval and generation quality",
    "Partner with product to ship measurable improvements every sprint"
  ],
  "required_skill_slugs": ["python", "pytorch", "fastapi", "docker", "kubernetes"],
  "preferred_skill_slugs": ["langchain", "pgvector", "prometheus"]
}
```

  **Authoring rules for the ~40 rows** (the implementer writes the rest following the shape above):
  - **Roles:** spread across ML engineering, data science, applied research, backend, frontend, full-stack, platform/infra, MLOps, data engineering, and 2–3 EM/lead rows.
  - **Seniority mix:** ≥3 `intern`/`junior`, ~15 `mid`, ~15 `senior`, ~5 `staff`/`principal`, 2–3 `lead`/`manager`.
  - **work_mode:** roughly ⅓ each `remote` / `hybrid` / `onsite`.
  - **Companies:** invent plausible names + domains; do NOT use real company names. Vary `location` (include several "Remote" and non-US).
  - **Salary:** realistic ranges for the role+seniority+region; every row has a range; `salary_currency` matches the region; `salary_period` almost always `"year"` (1–2 `"hour"` contract rows).
  - **Skills:** every slug in `required_skill_slugs` / `preferred_skill_slugs` MUST exist in `backend/app/domain/skills/taxonomy.json`. 3–7 required, 1–4 preferred per row.
  - **`description`:** 2–4 sentences, concrete, no fluff. **`responsibilities`:** 3–5 bullets.
  - **`key`:** unique kebab-case, stable (used as the upsert key).
  - **`posted_at`:** ISO dates spread over the ~6 weeks before 2026-09-02.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/jobs/test_seed.py` (DB):

```python
from sqlalchemy import func, select

from app.models.job import Job, JobChunk
from app.seed import load_jobs_demo, seed_jobs


async def test_demo_file_is_well_formed():
    rows = await load_jobs_demo()
    assert 30 <= len(rows) <= 60
    keys = [r["key"] for r in rows]
    assert len(keys) == len(set(keys))
    for r in rows:
        assert r["title"] and r["company"] and r["description"]
        assert r["work_mode"] in {"remote", "hybrid", "onsite"}
        assert r["seniority"] in {
            "intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager"
        }
        assert isinstance(r["responsibilities"], list) and r["responsibilities"]
        assert isinstance(r["required_skill_slugs"], list) and r["required_skill_slugs"]


async def test_demo_skill_slugs_all_exist_in_taxonomy():
    from app.seed import load_taxonomy

    taxo = {e["slug"] for e in await load_taxonomy()}
    for r in await load_jobs_demo():
        for slug in [*r["required_skill_slugs"], *r.get("preferred_skill_slugs", [])]:
            assert slug in taxo, f"{r['key']}: unknown skill slug {slug!r}"


async def test_seed_jobs_populates_ready_rows_with_embedded_chunks(db_session):
    # taxonomy must be present so skill slugs resolve
    from app.seed import seed_skills
    await seed_skills(db_session)

    n = await seed_jobs(db_session)
    assert n >= 30

    ready = (await db_session.execute(
        select(func.count()).select_from(Job).where(Job.is_seed.is_(True), Job.status == "ready")
    )).scalar_one()
    assert ready >= 30

    missing = (await db_session.execute(
        select(func.count()).select_from(JobChunk).where(JobChunk.embedding.is_(None))
    )).scalar_one()
    assert missing == 0

    # idempotent
    n2 = await seed_jobs(db_session)
    total = (await db_session.execute(
        select(func.count()).select_from(Job).where(Job.is_seed.is_(True))
    )).scalar_one()
    assert n2 == n and total == n
```

- [ ] **Step 2: Run — expect import failure / empty file.**

- [ ] **Step 3: Author `jobs.demo.json`** (~40 rows per the rules above).

- [ ] **Step 4: Implement `load_jobs_demo` + `seed_jobs` + CLI** in `backend/app/seed.py`. Reuse `seed_skills`'s `session=None` dual-path idiom. Upsert each `Job` via `insert(Job).values(source_ref=row["key"], is_seed=True, ...).on_conflict_do_update(index_elements=["source_ref"], index_where=text("is_seed"), set_={...})` — the partial unique index `uq_jobs_seed_source_ref` (created in Task 1) is the conflict target. After the row upsert, `select` the job id back by `source_ref`, `DELETE FROM job_chunks WHERE job_id = :id`, then insert the freshly-embedded chunks. Keep it one commit per green step is not required inside seed authoring — commit once at Step 6.

- [ ] **Step 5: Run** `"$UV" run pytest tests/domain/jobs/test_seed.py -q` (DB) → PASS (or `--collect-only` + CI). `"$UV" run pytest tests/domain/jobs/test_seed.py::test_demo_file_is_well_formed tests/domain/jobs/test_seed.py::test_demo_skill_slugs_all_exist_in_taxonomy -q` runs without a DB — must PASS locally. `ruff`/`mypy`/`lint-imports` clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/jobs/jobs.demo.json backend/app/seed.py backend/tests/domain/jobs/test_seed.py
git commit -m "feat(jobs): ~40-posting demo dataset + seed_jobs loader"
```

---

## Task 8: frontend — types + endpoints + query keys

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/api/endpoints.ts`
- Modify: `frontend/lib/query.ts`
- Test: `frontend/tests/api/endpoints.test.ts` (extend)

**Interfaces — Produces:**
- `types.ts`:
  ```ts
  export type JobSkillRef = { slug: string; label: string; weight: number };
  export type JobStatus = "ingesting" | "ready" | "failed";
  export interface JobCard {
    id: string; title: string | null; company: string | null; location: string | null;
    work_mode: "remote" | "hybrid" | "onsite" | null;
    seniority: string | null; employment_type: string | null;
    salary_min: number | null; salary_max: number | null;
    salary_currency: string | null; salary_period: string | null;
    is_seed: boolean; status: JobStatus;
    posted_at: string | null; created_at: string;
    required_skills: JobSkillRef[];
  }
  export interface JobDetail extends JobCard {
    company_domain: string | null;
    experience_min_years: number | null; experience_max_years: number | null;
    description: string | null; responsibilities: string[];
    preferred_skills: JobSkillRef[]; raw_text: string;
  }
  export interface JobListResponse { items: JobCard[]; total: number; limit: number; offset: number }
  export interface JobQuery {
    q?: string; work_mode?: string; seniority?: string; location?: string;
    employment_type?: string; salary_min?: number; skills?: string; sort?: string;
    limit?: number; offset?: number;
  }
  ```
- `endpoints.ts` — a `jobs` group on the object returned by `makeApi`:
  ```ts
  jobs: {
    async list(query: JobQuery = {}) {
      const qs = new URLSearchParams(
        Object.entries(query).filter(([, v]) => v !== undefined && v !== "")
          .map(([k, v]) => [k, String(v)]),
      ).toString();
      return f<JobListResponse>(`/api/v1/jobs${qs ? `?${qs}` : ""}`);
    },
    async get(id: string) { return f<JobDetail>(`/api/v1/jobs/${id}`); },
    async create(raw_text: string) {
      return f<{ id: string; status: JobStatus }>("/api/v1/jobs", json("POST", { raw_text }));
    },
    async patch(id: string, body: { title?: string }) {
      return f<JobDetail>(`/api/v1/jobs/${id}`, { method: "PATCH", body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" } });
    },
    async remove(id: string) { return f<void>(`/api/v1/jobs/${id}`, { method: "DELETE" }); },
  },
  ```
- `query.ts` — add to `qk`:
  ```ts
  jobs: ["jobs"] as const,
  jobsList: (q: Record<string, unknown>) => ["jobs", "list", q] as const,
  job: (id: string) => ["jobs", id] as const,
  ```

- [ ] **Step 1: Extend `frontend/tests/api/endpoints.test.ts`**

```ts
describe("jobs", () => {
  it("list serialises query params and GETs /jobs", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return { items: [], total: 0 }; }) as unknown as Fetcher);
    await api.jobs.list({ q: "rust", work_mode: "remote", limit: 12 });
    expect(calls[0]).toBe("/api/v1/jobs?q=rust&work_mode=remote&limit=12");
  });
  it("list with no params GETs bare /jobs", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return { items: [] }; }) as unknown as Fetcher);
    await api.jobs.list();
    expect(calls[0]).toBe("/api/v1/jobs");
  });
  it("create POSTs { raw_text } to /jobs", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return { id: "j1", status: "ingesting" }; }) as unknown as Fetcher);
    await api.jobs.create("Senior ML Engineer ...");
    expect(calls[0].path).toBe("/api/v1/jobs");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ raw_text: "Senior ML Engineer ..." });
  });
  it("remove DELETEs /jobs/{id}", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return undefined; }) as unknown as Fetcher);
    await api.jobs.remove("j1");
    expect(calls[0].path).toBe("/api/v1/jobs/j1");
    expect(calls[0].init?.method).toBe("DELETE");
  });
});
```

- [ ] **Step 2: Run** `pnpm exec vitest run tests/api/endpoints.test.ts` → the 4 new cases FAIL.
- [ ] **Step 3: Implement** the three files above.
- [ ] **Step 4: Run** `pnpm exec vitest run tests/api/endpoints.test.ts && pnpm exec tsc --noEmit && pnpm lint` → all green.
- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/lib/query.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(jobs): frontend api types, endpoints, query keys"
```

---

## Task 9: frontend — `useJobEvents` + `JobCard` + `JobFilters`

**Files:**
- Create: `frontend/hooks/useJobEvents.ts`
- Create: `frontend/components/jobs/JobCard.tsx`
- Create: `frontend/components/jobs/JobFilters.tsx`
- Test: `frontend/tests/jobs/job-card.test.tsx`
- Test: `frontend/tests/jobs/job-filters.test.tsx`

**Interfaces:**
- Consumes: `JobCard`, `JobStatus` types (Task 8); `useAuth` (`@/providers/AuthProvider`); `Button`, `Skeleton` UI primitives; `useRouter`, `useSearchParams`, `usePathname` (`next/navigation`).
- Produces:
  - `useJobEvents.ts` — `export function useJobEvents(jobId: string | null, opts?: { enabled?: boolean; baseDelayMs?: number }): { status: JobStatus | null; message: string | null; done: boolean; error: string | null }`. **Copy `frontend/hooks/useResumeEvents.ts` verbatim**, rename the type to `JobEventState`, swap the URL to `/api/v1/jobs/${jobId}/events`, `ResumeStatus`→`JobStatus`, and treat `done` as `status ∈ {"ready","failed"}` (the backend `done` event already carries the terminal status — no logic change needed beyond the URL + type names).
  - `JobCard.tsx` — `export function JobCard({ job }: { job: JobCard })`. A `<Link href={`/jobs/${job.id}`}>` card: title (fallback "Untitled role"), company · location line, chips for `work_mode` + `seniority` + `employment_type` (skip nulls), a salary range string (`fmtSalary(job)` — `"$190k–$240k/yr"` style; helper lives in the file), up to 5 `required_skills` label chips + a "+N" overflow chip, and a small "Sample" badge when `job.is_seed`. **No match %** — a `{/* match score: Phase 5 */}` comment marks where it goes. Tailwind tokens only (`text-text`, `text-text-muted`, `bg-surface`, `border-border`, `rounded-[var(--radius)]`, `rounded-full`).
  - `JobFilters.tsx` — `export function JobFilters()`. A search `<input>` (debounced 300ms) + `<select>`s for `work_mode` (remote/hybrid/onsite), `seniority` (the 8 values), and a `salary_min` `<select>` (e.g. none/100k/150k/200k). Every control reads its value from `useSearchParams()` and writes via `router.replace(`${pathname}?${next}`)` (preserving other params, dropping empty ones). A "Clear filters" button when any param is set. No local state beyond the debounce timer.

- [ ] **Step 1: Write failing tests**

`frontend/tests/jobs/job-card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JobCard } from "@/components/jobs/JobCard";
import type { JobCard as JobCardT } from "@/lib/api/types";

const base: JobCardT = {
  id: "j1", title: "Senior ML Engineer", company: "Nimbus AI", location: "Remote",
  work_mode: "remote", seniority: "senior", employment_type: "Full-time",
  salary_min: 190000, salary_max: 240000, salary_currency: "USD", salary_period: "year",
  is_seed: true, status: "ready", posted_at: null, created_at: "2026-08-20T00:00:00Z",
  required_skills: [
    { slug: "python", label: "Python", weight: 0.9 },
    { slug: "pytorch", label: "PyTorch", weight: 0.8 },
  ],
};

describe("JobCard", () => {
  it("renders title, company, salary and skill chips, links to detail", () => {
    render(<JobCard job={base} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/jobs/j1");
    expect(screen.getByText("Senior ML Engineer")).toBeInTheDocument();
    expect(screen.getByText(/Nimbus AI/)).toBeInTheDocument();
    expect(screen.getByText(/190k/)).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText(/sample/i)).toBeInTheDocument();
  });

  it("falls back gracefully when fields are null", () => {
    render(<JobCard job={{ ...base, title: null, company: null, salary_min: null, salary_max: null, is_seed: false }} />);
    expect(screen.getByText(/untitled role/i)).toBeInTheDocument();
    expect(screen.queryByText(/sample/i)).not.toBeInTheDocument();
  });
});
```

`frontend/tests/jobs/job-filters.test.tsx` — render inside `renderWithProviders` (for the router), type in the search box, assert `mockReplace`/`mockPush` was called with a `q=` query string; pick a `work_mode` option, assert the URL update. (Use the `test/utils` router spies.)

- [ ] **Step 2: Run — expect failures.**
- [ ] **Step 3: Implement** the three files.
- [ ] **Step 4: Run** `pnpm exec vitest run tests/jobs/ && pnpm exec tsc --noEmit && pnpm lint` → green.
- [ ] **Step 5: Commit**

```bash
git add frontend/hooks/useJobEvents.ts frontend/components/jobs/JobCard.tsx frontend/components/jobs/JobFilters.tsx frontend/tests/jobs/job-card.test.tsx frontend/tests/jobs/job-filters.test.tsx
git commit -m "feat(jobs): useJobEvents hook, JobCard, JobFilters"
```

---

## Task 10: frontend — Discovery page + `AddJobDialog`

**Files:**
- Create: `frontend/components/jobs/AddJobDialog.tsx`
- Create: `frontend/app/(app)/jobs/page.tsx`
- Test: `frontend/tests/jobs/add-job-dialog.test.tsx`
- Test: `frontend/tests/jobs/discovery-page.test.tsx`

**Interfaces:**
- Consumes: `api.jobs` (Task 8); `qk.jobsList` (Task 8); `JobCard`, `JobFilters` (Task 9); `useJobEvents` (Task 9); `useAuth`, `useToast`, `Button`, `Textarea`, `Skeleton`, `Card`; `EmptyState` (`@/components/common/EmptyState`); `useRouter`, `useSearchParams`.
- Produces:
  - `AddJobDialog.tsx` — `export function AddJobDialog()`. A `Button` "Add a job" that reveals a `<Textarea>` (paste the JD) + "Ingest" button. On submit: `react-hook-form` + `zod` (`raw_text` min 40 chars), `useMutation(() => api.jobs.create(raw_text))`; `onSuccess` → `toast({ title: "Ingesting the posting…" })`, set the new job id into local state so `useJobEvents(newId)` runs; when its `status === "ready"` → `queryClient.invalidateQueries({ queryKey: qk.jobs })` + `router.push(`/jobs/${newId}`)`; when `status === "failed"` → `toast({ title: "We couldn't read that posting.", variant: "danger" })` and clear. Mirrors the résumé upload flow in `app/(app)/resume/page.tsx` (mutation + SSE + navigate).
  - `jobs/page.tsx` — `"use client"` default export `JobsPage`. Reads filters from `useSearchParams()` → a `JobQuery` object → `useQuery({ queryKey: qk.jobsList(query), queryFn: () => api.jobs.list(query) })`. Layout: page header ("Jobs" + one-line subtitle) with `<AddJobDialog />` on the right; `<JobFilters />`; then pending → a skeleton grid (6 `<Skeleton>` cards); error → `ErrorState`; empty → `<EmptyState title="No jobs match" description="Try clearing filters, or paste a job description to add one." />`; else a responsive grid of `<JobCard>` + a "{total} roles" count + Prev/Next paging via `offset` in the URL.

- [ ] **Step 1: Write failing tests**

`frontend/tests/jobs/discovery-page.test.tsx` — `renderWithProviders(<JobsPage />, { api: { jobs: { list: vi.fn(async () => ({ items: [<one JobCard>], total: 1, limit: 24, offset: 0 })) } } })`; assert the card title renders and the "1 role" count shows; a second test with `list` returning `{ items: [], total: 0 }` asserts the empty state.

`frontend/tests/jobs/add-job-dialog.test.tsx` — render, click "Add a job", type <40 chars → submit disabled/zod error; type a valid JD, submit → `api.jobs.create` called once with the text; then (mock `useJobEvents` via a sph… simplest: mock the module `vi.mock("@/hooks/useJobEvents", () => ({ useJobEvents: () => ({ status: "ready", done: true, message: null, error: null }) }))`) assert `mockPush` was called with `/jobs/<id>`.

- [ ] **Step 2: Run — expect failures.**
- [ ] **Step 3: Implement** both files.
- [ ] **Step 4: Run** `pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint` — **whole suite** (Discovery is a new route but `AddJobDialog` mocks touch shared modules). Green.
- [ ] **Step 5: Commit**

```bash
git add frontend/components/jobs/AddJobDialog.tsx "frontend/app/(app)/jobs/page.tsx" frontend/tests/jobs/add-job-dialog.test.tsx frontend/tests/jobs/discovery-page.test.tsx
git commit -m "feat(jobs): Discovery page + AddJobDialog paste-a-JD flow"
```

---

## Task 11: frontend — Job Detail page + nav

**Files:**
- Create: `frontend/app/(app)/jobs/[id]/page.tsx`
- Modify: `frontend/components/layout/nav-items.ts` (flip `/jobs` to `ready: true`)
- Test: `frontend/tests/jobs/job-detail-page.test.tsx`

**Interfaces:**
- Consumes: `api.jobs.get` / `api.jobs.remove` (Task 8); `qk.job` (Task 8); `useJobEvents` (Task 9); `useAuth`, `useToast`, `useRouter`, `useParams`; `Button`, `Card`, `Skeleton`; `ErrorState`.
- Produces — `jobs/[id]/page.tsx` `"use client"` default export `JobDetailPage`:
  - `const { id } = useParams<{ id: string }>()`; `useQuery({ queryKey: qk.job(id), queryFn: () => api.jobs.get(id) })`.
  - If `data.status === "ingesting"` → render a small "We're reading this posting…" panel driven by `useJobEvents(id)`; invalidate `qk.job(id)` when it reports `ready`.
  - Ready layout: header (title, company · location, chips, salary); a **"Match & preparation"** `<Card>` placeholder with muted copy — `"Your fit for this role — how your skills line up and what to brush up on — lands in the next release."` and a **disabled** `Button` "Prepare application" with a `title`/`aria-disabled` note (`{/* Phase 5 match breakdown + Phase 8 Prepare Application wiring go here */}`); the JD proper — `description`, a "Responsibilities" list, "Required skills" / "Preferred skills" chip rows, an "Experience" line, and a collapsible `<details>` "Original posting" showing `raw_text`.
  - For `job.is_seed === false`: a "Remove" `Button variant="ghost"` → `useMutation(() => api.jobs.remove(id))` → `onSuccess` toast + `router.push("/jobs")` + invalidate `qk.jobs`. For seed jobs: no Remove button.
- `nav-items.ts` — change the `/jobs` entry to `ready: true`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/jobs/job-detail-page.test.tsx` — mock `useParams` to `{ id: "j1" }` (via `test/utils` — `useParams` is already mocked there to `() => ({})`; override per-test with `vi.mocked`); `renderWithProviders(<JobDetailPage />, { api: { jobs: { get: vi.fn(async () => (<a ready JobDetail with description + responsibilities + is_seed:true>)) } } })`; assert the title, a responsibility bullet, and the "Match & preparation" placeholder copy render, and that **no "Remove" button** appears for a seed job. Second test: `is_seed: false` → "Remove" present; clicking it calls `api.jobs.remove` and `mockPush("/jobs")`.

- [ ] **Step 2: Run — expect failure.**
- [ ] **Step 3: Implement** the page + flip the nav flag.
- [ ] **Step 4: Run** `pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint` — whole suite green (nav-items change touches `Sidebar`/`MobileNav` render paths — their existing tests must stay green).
- [ ] **Step 5: Commit**

```bash
git add "frontend/app/(app)/jobs/[id]/page.tsx" frontend/components/layout/nav-items.ts frontend/tests/jobs/job-detail-page.test.tsx
git commit -m "feat(jobs): Job Detail page + enable Jobs nav"
```

---

## Task 12: verification & Phase 4 completion report

- [ ] **Step 1: Full backend gate** — from `backend/`: `"$UV" run ruff check . && "$UV" run lint-imports && "$UV" run mypy app && "$UV" run pytest -q` — ruff clean; **2 import contracts kept**; mypy clean; pytest green (Phases 0–4). DB/Redis suites verify in CI; locally confirm `"$UV" run pytest -q --collect-only` is error-free and the no-DB suites pass (`tests/domain/jobs/test_extractor.py`, `test_ingestor.py`, `test_chunking.py`, and the two `test_seed.py::test_demo_*` cases).

- [ ] **Step 2: Seed smoke** — from `backend/`, against the CI database (or document "not run — no local DB"): `"$UV" run python -m app.seed all` → prints a skills count then a jobs count ≥ 30; a second run is idempotent (same counts). The `tests/domain/jobs/test_seed.py::test_seed_jobs_populates_ready_rows_with_embedded_chunks` case already encodes this — confirm it is collected and (in CI) green.

- [ ] **Step 3: Full frontend gate** — from `frontend/`: `pnpm lint && pnpm exec tsc --noEmit && pnpm exec vitest run` — all green. Record the file/test counts (baseline before Phase 4: 30 files / 79 tests).

- [ ] **Step 4: OpenAPI sanity** — `POST /api/v1/jobs`, `GET /api/v1/jobs`, `GET /api/v1/jobs/{job_id}`, `GET /api/v1/jobs/{job_id}/events`, `PATCH /api/v1/jobs/{job_id}`, `DELETE /api/v1/jobs/{job_id}` all present; no `/jobs/{job_id}/research` path (deferred).

- [ ] **Step 5: Fill the completion report below, commit** `docs: Phase 4 completion report`.

---

## Phase 4 completion report

_Executed 2026-09-02 (12 tasks, subagent-driven). Ledger: `.superpowers/sdd/2026-09-02-phase-4-job-ingestion/`._

- **What changed:**
  - **Migration `0007_jobs`** (`alembic/versions/0007_jobs.py`, `app/models/job.py`) — `jobs` table (nullable `user_id` = seed; `raw_text`; all structured columns; `responsibilities text[]`; `required_skills`/`preferred_skills`/`structured`/`extraction_meta` JSONB; `status` ingesting/ready/failed; `search_tsv` generated `to_tsvector` STORED column; 6 CHECKs) + `job_chunks` (cascade FK, `section`, `content`, `embed_model`/`embed_dim`, `embedding Vector(1024)`, generated `chunk_tsv`). Indexes: GIN(search_tsv), GIN(structured), GIN(required_skills jsonb_path_ops), `pg_trgm` on title/company, HNSW on the chunk embedding, partial-unique `uq_jobs_seed_source_ref` on `(source_ref) WHERE is_seed`. Chain `0006_skills → 0007_jobs`, linear.
  - **`JobExtractor`** (`app/domain/jobs/extractor.py`) — `JobExtraction` / `JDSkill` Pydantic models + one `llm.complete(schema=JobExtraction)` call; mirrors `ResumeExtractor`.
  - **`JobIngestor` + chunker** (`app/domain/jobs/ingestor.py`, `chunking.py`) — `clean()` (whitespace/blank-line collapse, per-line lstrip, length cap, empty guard) + `chunk_job()` (section-aware — description/responsibilities/requirements — overlapping word windows, whitespace-token estimate).
  - **`JobService`** (`app/domain/jobs/service.py`) — `create` (validate ≥40 chars, insert `status="ingesting"`, deferred `enqueue("ingest_job", …, _defer_by=2.0, _job_id=…)`, audit), `get` (own-or-seed), `list_` (the Discovery query: `websearch_to_tsquery` on `search_tsv` OR title/company ILIKE, + `work_mode`/`seniority`/`employment_type`/`location`/`salary_min` filters + `required_skills @> [{slug}]` per skill, count-of-subquery for `total`, `created_at DESC` + limit/offset), `update`/`delete` (user jobs only → 404 for seed/cross-user), `apply_ingestion` (worker callback: write structured cols, replace `job_chunks`).
  - **`ingest_job` worker task** (`app/worker/tasks/jobs.py`, `worker/main.py`, `worker/tasks/__init__.py`, `app/core/events.py`) — verbatim `_session_for` seam; pipeline clean → extract → **`_normalize_enums`** (coerce `work_mode`/`seniority`/`salary_period`/`salary_currency` onto the CHECK vocabularies, drift → `None`, never fail the ingest) → `SkillNormalizer` → `chunk_job` → `embed_documents` → `apply_ingestion` → SSE `status`/`ready`; `except` block carries the Phase-3 `job_try < MAX_TRIES` retry guard before dead-letter, `status="failed"` + `error` on terminal failure. New `job_channel(job_id)` in `events.py`. `confirm_profile` is **not** touched (jobs enqueue only from `POST /jobs`).
  - **API** (`app/api/v1/jobs.py`, `schemas/jobs.py`, `router.py`) — `POST /jobs` `{raw_text}` → 202 `JobRefOut`; `GET /jobs` (query params → `JobFilters`, `limit` clamped 1–60, paginated `JobListOut`); `GET /jobs/{id}` `JobDetailOut`; `GET /jobs/{id}/events` (SSE, `resume_events` body copied with the swaps); `PATCH`/`DELETE` (user jobs only). Explicit `_card(job)` / `_detail(job)` mappers build `JobSkillOut` from each ORM dict (no `from_attributes` on the skills field).
  - **Seed** (`app/domain/jobs/jobs.demo.json` — 41 rows; `app/seed.py` — `load_jobs_demo`, `seed_jobs(session=None)`, CLI `skills|jobs|all`) — pre-structured rows upsert on the partial-unique index as `status="ready"` seed jobs, skill slugs resolved against `skills`, chunked + embedded at seed time.
  - **Frontend** — `lib/api/types.ts` (+`JobCard`/`JobDetail`/`JobSkillRef`/`JobListResponse`/`JobQuery`/`JobStatus`), `lib/api/endpoints.ts` (+`api.jobs` group), `lib/query.ts` (+`qk.jobs`/`jobsList`/`job`); `hooks/useJobEvents.ts` (verbatim copy of `useResumeEvents`); `components/jobs/{JobCard,JobFilters,AddJobDialog}.tsx`; `app/(app)/jobs/page.tsx` (Discovery — filters-in-URL, skeleton/error/empty states, card grid, offset paging) + `app/(app)/jobs/[id]/page.tsx` (Job Detail — ingesting panel, JD render, "Match & preparation" placeholder, Remove for user jobs); `components/layout/nav-items.ts` flips Jobs to `ready: true`.
  - **Infra:** `backend/pyproject.toml` `addopts` gained `--import-mode=importlib` (Ruling R9 — two `test_extractor.py` / `test_service.py` basename collisions were aborting `pytest` collection under the default `prepend` mode).
- **Why:** a browsable, structured job corpus is the substrate Phase 5 scores against, Phase 7's agent researches, and Phase 8 tailors résumés for.
- **Files changed / new deps:** ~19 backend files (7 new source: `models/job.py`, `alembic/versions/0007_jobs.py`, `domain/jobs/{__init__,extractor,ingestor,chunking,service}.py`, `worker/tasks/jobs.py`; `domain/jobs/jobs.demo.json`; edits to `app/seed.py`, `app/core/events.py`, `app/worker/main.py`, `app/worker/tasks/__init__.py`, `app/api/v1/{jobs,schemas/jobs,router}.py`, `app/models/__init__.py`, `tests/conftest.py`, `pyproject.toml`; 8 new test files) + ~13 frontend files (`hooks/useJobEvents.ts`, `components/jobs/{JobCard,JobFilters,AddJobDialog}.tsx`, `app/(app)/jobs/{page,[id]/page}.tsx`, `lib/api/{types,endpoints}.ts`, `lib/query.ts`, `components/layout/nav-items.ts`, + 6 new `tests/jobs/*` + endpoints.test.ts). **No new dependencies** — pgvector, `LLMProvider`, `EmbeddingsProvider` (fake in CI), ARQ, `pg_trgm` (enabled in `0001_bootstrap`) all already present.
- **How to test:** `cd backend && uv run pytest tests/domain/jobs tests/models/test_job_model.py tests/worker/test_jobs_task.py tests/api/test_jobs.py -q` · `cd frontend && pnpm exec vitest run`
- **Regression check:** Phases 0–3 suites green; migration chain `0001 → … → 0007` linear; `/auth`, `/resumes`, `/profile` routes unchanged; `import-linter` — 2 contracts kept; `ruff` / `mypy app` (80 source files) clean; frontend `tsc --noEmit` + `next lint` clean; `_bucket` already routed `POST /jobs` to the upload tier (no rate-limit change); OpenAPI exposes exactly `POST|GET /jobs`, `GET|PATCH|DELETE /jobs/{job_id}`, `GET /jobs/{job_id}/events` (no `/research`).
- **Baseline:** 181 backend tests → 211 (`pytest --collect-only`, no collection errors); 30 frontend files / 79 tests → 35 files / 93 tests (`vitest run`, all green).
- **Deviations:**
  - Demo dataset **41 rows**, not the spec's 60–100 (approved scope decision — enough to exercise every filter, no LLM dependency at seed).
  - **Paste-only** `POST /jobs` (`{raw_text}`); multipart / PDF JD upload deferred (`source="user_upload"` is a valid CHECK value, unused).
  - **One `ingest_job` task**, not the résumé pipeline's two-task split.
  - Chunker lives in `app/domain/jobs/`, not `app/domain/rag/` (the `rag` package is Phase 6).
  - `_normalize_enums` in the worker (Ruling R10) — the plan didn't cover coercing the LLM's free-text enum fields; without it a drifting `work_mode="Remote"` trips a CHECK and aborts the whole ingest.
  - `--import-mode=importlib` added to `pyproject.toml` (Ruling R9) — a repo-infra fix outside any task's file scope.
  - `sort=match` / `has_match` accepted as query params but **no-op** (Phase 5).
- **Not verified here:** hybrid/vector Discovery retrieval (Phase 6 — `job_chunks` populated, not queried); real LLM extraction quality (fake provider only); match scoring + "Why this match?" (Phase 5); Job Research Agent `/jobs/{id}/research` (Phase 7); "Prepare Application" wiring (Phase 8); file/PDF JD upload. DB/Redis-backed suites (`test_job_model`, `test_service`, `test_jobs_task`, `test_jobs`, `test_seed::test_seed_jobs_*`) verify in CI — locally only `--collect-only` (211, clean) + the no-DB jobs suites (11 passed) ran.
- **Deferred minors** (from per-task reviews, for the whole-branch review to triage): `_resolve`/`meta["unmatched"]` recall gap when a skill appears in both required+preferred with case-differing raw (`ingest_job`) — key `matches` by `SkillNormalizer._norm`; `_card`/`_detail` read `s["slug"]`/`["label"]`/`["weight"]` unguarded from free-form JSONB — use `.get()` (mirrors Phase-3 `/profile/skills` M9); `text` local var shadows the module `text` import in `seed_skills._run` (pre-existing); a few coined seed company names sit near real-ish entities (invented domains, low impact); `qk.jobsList` param typed `Record<string, unknown>` forces a `{ ...query }` spread at the call site — widen to `JobQuery`; `JobFilters` search `<input key={q}>` drops focus ~300ms after a pause when the debounce commits `q` to the URL (Phase-5 polish).

---

## Self-Review

**1. Spec coverage (Phase 4 of §9 + §1.7 + §2.2 `/jobs` + §5 `jobs`/`job_chunks` + §6.4 SSE + §7.1):**
- seed loader → Task 7 (`seed_jobs`, `python -m app.seed jobs|all`). ✓
- `POST /jobs` → Task 6 (202, `{raw_text}`). ✓ (multipart deferred, flagged.)
- `ingest_job` → Task 5 (one ARQ task). ✓
- `JobExtractor` → Task 2. ✓ `JobIngestor` → Task 3. ✓
- `job_chunks` embeddings → Tasks 1 (table) + 5 (populated on ingest) + 7 (populated on seed). ✓ (retrieval is Phase 6, flagged.)
- Discovery (search + filters + cards) → Tasks 4 (`list_` query) + 6 (`GET /jobs`) + 9 (`JobCard`, `JobFilters`) + 10 (page). ✓
- Job Detail (JD only) → Task 11. ✓
- `GET /jobs/{id}/events` SSE → Task 5 (`job_channel`) + Task 6 (route, copied from `resume_events`). ✓
- `PATCH` / `DELETE` (user jobs only) → Tasks 4 (`_owned`) + 6. ✓
- `/jobs/{id}/research` → **deferred to Phase 7**, flagged in Global Constraints + Task 6. ✓
- "Done when: fresh clone shows demo jobs; paste a JD → appears structured" → Task 7 (seed) + Tasks 5/6/10 (paste → ingest → detail). ✓

**2. Placeholder scan:** Tasks 1–9 carry literal code + tests. Tasks 10–11 carry full Produces contracts + concrete test specs and describe the component bodies against them (accepted style, Phases 2b/3). Task 7's demo JSON is specified by shape + one worked example + explicit authoring rules + a test that enforces slug validity and shape (same approach as Phase 3's taxonomy). The `ingest_job` `except` block, the `_session_for` verbatim copy, and the `resume_events`→`job_events` copy are each named explicitly. No "TBD".

**3. Type consistency:**
- `Job` / `JobChunk` column names (Task 1) are consumed by Tasks 4, 5, 6, 7 under identical names.
- `JobExtraction` / `JDSkill` (Task 2) — consumed by Tasks 3 (`chunk_job`), 5 (`ingest_job`), 7 (`seed_jobs`).
- `JobChunkDraft` (Task 3) — `{section, chunk_index, content, token_count}` — consumed by Tasks 4 (`apply_ingestion` signature) + 5.
- `JobFilters` (Task 4) — consumed by Task 6's `GET /jobs` param mapping.
- `job_channel` (Task 5) — consumed by Task 6's SSE route.
- FE `JobCard` / `JobDetail` / `JobQuery` / `JobListResponse` (Task 8) — consumed by Tasks 9, 10, 11; mirror the backend `JobCardOut` / `JobDetailOut` / `JobListOut` field names from Task 6.
- `useJobEvents` return shape (Task 9) — consumed by Tasks 10, 11.
- Migration chain `0006_skills` → `0007_jobs` (Task 1). ✓
- **Fix applied during review:** Task 7's seed loader upserts on `source_ref`, so Task 1's migration + model now carry the partial-unique index `uq_jobs_seed_source_ref` on `(source_ref) WHERE is_seed`. Task 7 Step 4 uses it as the `on_conflict` target. No forward dependency remains.

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-09-02-phase-4-job-ingestion.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between, whole-branch review at the end.

**2. Inline Execution** — `superpowers:executing-plans`, batched with checkpoints.

**Environment:** `uv` at `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`; backend `ruff`/`mypy`/`lint-imports` + the no-DB job suites run locally; DB+Redis-backed tests (Tasks 1, 4, 5, 6, 7 and the worker/API tests) verify in CI. Frontend runs fully locally with `pnpm exec vitest run`. The skill-embedding path is exercised with the fake provider (deterministic); real providers land in Phase 6.
