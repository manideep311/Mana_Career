# Phase 5: Job Matching Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every job the user opens shows an explainable 0–100 match score — a per-dimension breakdown with ✓/△, strengths, skill gaps, and a one-paragraph plain-language narrative — and Discovery can filter/sort by it.

**Architecture:** A **pure, deterministic `MatchScorer`** compares a `ProfileSnapshot` (built from the Phase-3 `CareerProfile` + `profile_skills` + experiences/projects/education) against a `JobSnapshot` (built from the Phase-4 `Job` + its `job_chunks` embeddings) across 10 weighted dimensions, producing a `job_matches` row + one `match_components` row per dimension + `skill_gaps` rows for uncovered job skills. An ARQ task `score_match` runs the scorer, then makes **two non-scoring LLM calls** — one for the narrative (`MatchExplainer`), one batched call for per-gap rationales (`GapRationaleWriter`) — both non-fatal. The score is never touched by an LLM. Matching is **on-demand**: opening Job Detail (or a "Score" action) enqueues `score_match`; the frontend polls every 2 s while `status="scoring"`. `POST /matches/recompute {scope:"all"}` bulk-scores every visible job. `resume_version_id` is a nullable column (NULL = "matched against your current profile"); Phase 8 fills it when tailored résumé versions exist.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, ARQ + Redis, pgvector (`Vector`, `.cosine_distance()`), Pydantic v2, structlog. Frontend: Next.js 15 App Router, React 19, TS strict, Tailwind v4, `@tanstack/react-query` v5 (`refetchInterval` polling), Vitest + Testing Library + jsdom.

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` (§2.2 `/matches` + `/skill-gaps` routes, §4 `matching/` package, §5 `job_matches` + `match_components` + `skill_gaps` tables, D7 deterministic-scorer).

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtimes:** Python 3.12; PostgreSQL 16 + `pgvector` + `pg_trgm`; Redis 7. Migration chain: `0007_jobs` is head → this phase adds `0008_matches`.
- **PKs / timestamps / enums / soft-delete / audit:** exactly as Phases 1–4 — `uuid` `server_default=text("gen_random_uuid()")`; `created_at`/`updated_at` from `TimestampMixin` + a `set_updated_at()` trigger created in the migration; enums as `text` + named `CHECK`; `import-linter` layers `api > worker > domain > infra > core > models`, `domain/*` never imports `api`/`worker`.
- **Deterministic scorer (spec D7, §4):** `MatchScorer` is a **pure module** — no DB, no LLM, no I/O, no wall-clock. Same `(ProfileSnapshot, JobSnapshot, profile_embedding)` in → byte-identical `ScoreResult` out. The two LLM calls (`MatchExplainer`, `GapRationaleWriter`) **only produce prose** and are **non-fatal** — a failure leaves `explanation`/`rationale` NULL and the numeric result intact.
- **10 dimensions (spec §5), CHECK vocab verbatim:** `skill`, `experience`, `education`, `project`, `technology`, `location`, `role`, `seniority`, `salary`, `semantic`. Weights are hand-tuned constants in `weights.py` and MUST sum to `1.0` (a test asserts it). `contribution = raw_score * weight * 100`; `score = round(sum(contributions), 2)`.
- **Bands (spec §5):** `band ∈ {strong, good, partial, weak}` — `strong` if `score >= 80`, `good` if `>= 65`, `partial` if `>= 45`, else `weak`.
- **`scorer_version`:** a string constant `"v1"` in `weights.py`. `job_matches` is unique on `(user_id, job_id, scorer_version) WHERE resume_version_id IS NULL` (partial — Phase 5 only ever writes the current-profile case). Bumping `SCORER_VERSION` forces a fresh row. `inputs_hash` = `hashlib.sha256` hex of a canonical `json.dumps(..., sort_keys=True)` of the snapshot fields + `scorer_version`; an unchanged recompute is a no-op.
- **`resume_version_id`:** a **nullable `uuid` column with NO foreign key** (the `resume_versions` table is Phase 8). Every Phase-5 read/write filters `resume_version_id IS NULL`.
- **Embeddings:** the `semantic` dimension is a **direct cosine** — `1 - cosine_distance(profile_embedding, mean(job_chunk_embeddings))`, clamped to `[0, 1]`; `0.5` when either side is missing. `profile_embedding` comes from ONE `get_embeddings_provider(settings).embed_query(profile.summary_text)` call in the worker. The full `rag` hybrid retriever is Phase 6 — it will replace the cosine internals, not the dimension or its weight. CI runs `EMBEDDINGS_PROVIDER=fake`, `EMBED_DIM=1024` (`FakeEmbeddingsProvider` = deterministic unit vector per exact string — mechanics testable, values meaningless).
- **LLM:** `get_llm_provider(settings)` with `model=settings.llm_model_extraction`. CI runs `LLM_PROVIDER=fake` — `FakeLLMProvider.complete(schema=X)` returns `X` with every field stubbed. `MatchExplainer` / `GapRationaleWriter` handle an empty/failed structured payload by returning `None` (→ caller writes NULL, no raise).
- **Rate limits (spec §6.5):** `POST /matches`, `POST /matches/recompute` are **LLM tier** — add both to `app/core/rate_limit.py::_bucket` (`method == "POST" and path in (f"{base}/matches", f"{base}/matches/recompute")` → `"llm"`). Reads stay default tier.
- **Compute model:** on-demand only. `MatchService.get_or_create` returns a cached `status="ready"` row when its `scorer_version` **and** `inputs_hash` still match; otherwise inserts `status="scoring"` and `enqueue("score_match", str(job_match_id), _defer_by=2.0, _job_id=f"score_match:{job_match_id}")`. **No SSE** — the frontend polls `GET /matches/{id}` (or the match block on `GET /jobs/{id}`) every 2 s while `status="scoring"`. No automatic fan-out on profile edits or job ingest.
- **Worker discipline:** `score_match`'s module carries a **verbatim copy** of `_session_for()` from `app/worker/tasks/jobs.py` (not an import). The `except` block guards `if ctx.get("job_try", 1) < MAX_TRIES: raise` **before** `record_failure`, then sets `job_matches.status="failed"` + `error`. `MAX_TRIES` imported from `app.worker.tasks.resume` (as `worker/main.py` already does).
- **Deferred, flagged in the relevant task:** `resume_version_id` real values (Phase 8); `semantic` via the `rag` retriever (Phase 6); `scope="aggregate"` skill gaps + `POST /skill-gaps/aggregate` + roadmap linkage (Phase 12); the `understand_job` LangGraph flow (Phase 7); re-scoring on profile edit / roadmap-milestone progress (Phase 12); `job_matches.resume_version_id` FK.
- **Workflow:** TDD, DRY, YAGNI, commit per green step. Backend from `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run mypy app`, `uv run lint-imports` (uv at `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`). Frontend from `frontend/`: `pnpm exec vitest run`, `pnpm exec tsc --noEmit`, `pnpm lint` (`pnpm test` hangs). Pytest runs with `--import-mode=importlib` (`pyproject.toml`) — same-basename test files across packages are fine. DB/Redis-backed tests run in CI.

---

## File Structure

**Backend — new**
| File | Responsibility |
|---|---|
| `backend/alembic/versions/0008_matches.py` | `job_matches` + `match_components` + `skill_gaps` tables, indexes, triggers |
| `backend/app/models/match.py` | `JobMatch`, `MatchComponent`, `SkillGap` ORM models |
| `backend/app/domain/matching/__init__.py` | empty package marker |
| `backend/app/domain/matching/weights.py` | `SCORER_VERSION`, `WEIGHTS`, `BANDS`, `SENIORITY_LADDER` constants |
| `backend/app/domain/matching/scorer.py` | `ProfileSnapshot`, `JobSnapshot`, `Component`, `ScoreResult`, `score()` — pure |
| `backend/app/domain/matching/explainer.py` | `MatchExplainer` (narrative) + `GapRationaleWriter` (batched gap rationales) — LLM, prose only |
| `backend/app/domain/matching/gaps.py` | `GapDraft`, `derive_gaps(job, skill_component)` — pure |
| `backend/app/domain/matching/service.py` | `MatchService` — snapshots, get_or_create, apply_score, list, recompute, job_scores_for |
| `backend/app/worker/tasks/matching.py` | `score_match` ARQ task + verbatim `_session_for` |
| `backend/app/api/v1/schemas/matches.py` | `MatchRefOut`, `MatchComponentOut`, `MatchOut`, `RecomputeIn`, `MatchListOut` |
| `backend/app/api/v1/matches.py` | `/matches` router |
| `backend/app/api/v1/schemas/skill_gaps.py` | `SkillGapOut`, `SkillGapPatchIn` |
| `backend/app/api/v1/skill_gaps.py` | `/skill-gaps` router |

**Backend — modified**
| File | Change |
|---|---|
| `backend/app/models/__init__.py` | `from app.models import match as match` (alpha: after `job`, before `profile`) |
| `backend/app/core/rate_limit.py` | `_bucket`: `POST /matches` + `POST /matches/recompute` → `"llm"` tier |
| `backend/app/worker/tasks/__init__.py` | export `score_match` |
| `backend/app/worker/main.py` | register `score_match` in `WorkerSettings.functions` |
| `backend/app/api/v1/router.py` | `include_router(matches.router)` + `include_router(skill_gaps.router)` |
| `backend/app/domain/jobs/service.py` | `JobFilters` gains `has_match: bool` + `sort` accepts `"match"`; `_filtered`/`list_` LEFT JOIN `job_matches`; new `list_with_scores(...)` returning `(Job, score, band, status)` tuples |
| `backend/app/api/v1/jobs.py` | `_card` gains `match_score`/`match_band`/`match_status`; `list_jobs` uses `list_with_scores`; `get_job` attaches the caller's current-profile match summary; new `has_match` query param |
| `backend/app/api/v1/schemas/jobs.py` | `JobCardOut` gains `match_score: float \| None`, `match_band: str \| None`, `match_status: str \| None` |
| `backend/tests/conftest.py` | extend `_no_enqueue` to patch `app.domain.matching.service.enqueue` |

**Frontend — new**
| File | Responsibility |
|---|---|
| `frontend/hooks/useMatch.ts` | `useMatch(jobId)` — react-query with 2 s poll while `status === "scoring"` |
| `frontend/components/jobs/MatchBadge.tsx` | score pill for `JobCard` + a compact "Score" / "Scoring…" state |
| `frontend/components/jobs/WhyThisMatch.tsx` | Job Detail match panel — band, per-dimension ✓/△ rows, strengths, narrative |
| `frontend/components/jobs/SkillGaps.tsx` | the gap list inside `WhyThisMatch` — severity chip, rationale, status `<select>` |

**Frontend — modified**
| File | Change |
|---|---|
| `frontend/lib/api/types.ts` | `MatchBand`, `MatchStatus`, `MatchComponent`, `JobMatch`, `SkillGap`, `SkillGapStatus`; `JobCard`/`JobDetail` gain `match_score`/`match_band`/`match_status`; `JobQuery` gains `has_match?` |
| `frontend/lib/api/endpoints.ts` | `api.matches` group + `api.skillGaps` group |
| `frontend/lib/query.ts` | `qk.match(jobId)`, `qk.matchList(q)`, `qk.skillGaps(jobMatchId)` |
| `frontend/components/jobs/JobCard.tsx` | render `<MatchBadge>` at the `{/* match score: Phase 5 */}` slot |
| `frontend/components/jobs/JobFilters.tsx` | "Has match" checkbox → `has_match` param; add `"match"` (label "Best match") to the sort `<select>` |
| `frontend/app/(app)/jobs/[id]/page.tsx` | replace the "Match & preparation" placeholder `<Card>` with `<WhyThisMatch jobId={id} />` |
| `frontend/app/(app)/jobs/page.tsx` | a "Match all" `Button` in the header → `api.matches.recompute({scope:"all"})`; read `has_match` from the URL into the `JobQuery` |

---

## Task 1: `job_matches` + `match_components` + `skill_gaps` schema

**Files:**
- Create: `backend/alembic/versions/0008_matches.py`
- Create: `backend/app/models/match.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/test_match_model.py`

**Interfaces — Produces:**
- `JobMatch(Base, TimestampMixin)` — `__tablename__ = "job_matches"`. Columns: `id` uuid pk; `user_id` uuid FK `users.id` CASCADE not null; `resume_version_id: Mapped[uuid.UUID | None]` (`UUID(as_uuid=True)`, **no FK**); `job_id` uuid FK `jobs.id` CASCADE not null; `score: Mapped[decimal.Decimal | None] = mapped_column(Numeric(5, 2))`; `band: Mapped[str | None]` (String(16), CHECK `band is null or band in ('strong','good','partial','weak')`); `dimension_scores / strengths / gaps: Mapped[Any] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))` (`strengths`/`gaps` default `'[]'::jsonb`); `explanation: Mapped[str | None]` (Text); `explanation_meta: Mapped[dict[str, Any]]` (JSONB, default `'{}'::jsonb`); `inputs_hash: Mapped[str | None]` (String(64)); `scorer_version: Mapped[str]` (String(16), not null); `status: Mapped[str]` (String(16), not null, server_default `'scoring'`, CHECK `status in ('scoring','ready','failed')`); `error: Mapped[str | None]` (Text); `computed_at: Mapped[dt.datetime | None]`. `__table_args__`: `Index("uq_job_matches_profile", "user_id", "job_id", "scorer_version", unique=True, postgresql_where=text("resume_version_id IS NULL"))`, `Index("ix_job_matches_user_score", "user_id", text("score DESC"))`, `Index("ix_job_matches_job", "job_id")`.
- `MatchComponent(Base, TimestampMixin)` — `__tablename__ = "match_components"`. Columns: `id` uuid pk; `job_match_id` uuid FK `job_matches.id` CASCADE not null; `dimension: Mapped[str]` (String(20), not null, CHECK `dimension in ('skill','experience','education','project','technology','location','role','seniority','salary','semantic')`); `raw_score: Mapped[decimal.Decimal]` (Numeric(4, 3), not null); `weight: Mapped[decimal.Decimal]` (Numeric(4, 3), not null); `contribution: Mapped[decimal.Decimal]` (Numeric(5, 2), not null); `detail: Mapped[dict[str, Any]]` (JSONB, default `'{}'::jsonb`); `evidence: Mapped[list[dict[str, Any]]]` (JSONB, default `'[]'::jsonb`). `UniqueConstraint("job_match_id", "dimension", name="uq_match_components_dimension")`, `Index("ix_match_components_match", "job_match_id")`.
- `SkillGap(Base, TimestampMixin)` — `__tablename__ = "skill_gaps"`. Columns: `id` uuid pk; `user_id` uuid FK `users.id` CASCADE not null; `scope: Mapped[str]` (String(12), not null, CHECK `scope in ('job','aggregate')`); `job_match_id: Mapped[uuid.UUID | None]` (FK `job_matches.id` CASCADE); `skill_id` uuid FK `skills.id` CASCADE not null; `skill_slug: Mapped[str]` (String(120), not null); `skill_label: Mapped[str]` (String(160), not null); `severity: Mapped[str]` (String(16), not null, CHECK `severity in ('critical','important','nice_to_have')`); `frequency: Mapped[int]` (Integer, not null, server_default `'1'`); `rationale: Mapped[str | None]` (Text); `status: Mapped[str]` (String(12), not null, server_default `'open'`, CHECK `status in ('open','learning','closed')`); `addressed_by_roadmap_id: Mapped[uuid.UUID | None]` (`UUID(as_uuid=True)`, **no FK** — Phase 12). `UniqueConstraint("job_match_id", "skill_id", name="uq_skill_gaps_job_skill")`, `Index("ix_skill_gaps_user_scope", "user_id", "scope")`.
- Migration `revision = "0008_matches"`, `down_revision = "0007_jobs"`; `updated_at` triggers on all three tables (`CREATE TRIGGER trg_<table>_set_updated_at BEFORE UPDATE ON <table> FOR EACH ROW EXECUTE FUNCTION set_updated_at()`); `downgrade()` drops `skill_gaps`, then `match_components`, then `job_matches` (+ their triggers first).

- [ ] **Step 1: Write the failing model test**

`backend/tests/models/test_match_model.py`:

```python
import decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.job import Job
from app.models.match import JobMatch, MatchComponent, SkillGap
from app.models.skill import Skill
from app.models.user import User


async def _user_job(db_session, email="m@example.com"):
    u = User(email=email, password_hash="x", full_name="M")
    db_session.add(u)
    await db_session.flush()
    j = Job(user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60, title="J")
    db_session.add(j)
    await db_session.flush()
    return u, j


async def test_job_match_defaults_and_partial_unique(db_session):
    u, j = await _user_job(db_session)
    m = JobMatch(user_id=u.id, job_id=j.id, scorer_version="v1")
    db_session.add(m)
    await db_session.flush()
    got = (await db_session.execute(select(JobMatch).where(JobMatch.id == m.id))).scalar_one()
    assert got.status == "scoring"
    assert got.resume_version_id is None
    assert got.strengths == [] and got.gaps == [] and got.dimension_scores == {}
    # second current-profile row for the same (user, job, version) is rejected
    db_session.add(JobMatch(user_id=u.id, job_id=j.id, scorer_version="v1"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_match_component_dimension_check_and_unique(db_session):
    u, j = await _user_job(db_session, "m2@example.com")
    m = JobMatch(user_id=u.id, job_id=j.id, scorer_version="v1")
    db_session.add(m)
    await db_session.flush()
    db_session.add(MatchComponent(
        job_match_id=m.id, dimension="skill",
        raw_score=decimal.Decimal("0.900"), weight=decimal.Decimal("0.220"),
        contribution=decimal.Decimal("19.80"),
    ))
    await db_session.flush()
    db_session.add(MatchComponent(
        job_match_id=m.id, dimension="bogus",
        raw_score=decimal.Decimal("0.5"), weight=decimal.Decimal("0.1"),
        contribution=decimal.Decimal("5"),
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_skill_gap_severity_check_and_cascade(db_session):
    u, j = await _user_job(db_session, "m3@example.com")
    m = JobMatch(user_id=u.id, job_id=j.id, scorer_version="v1")
    s = Skill(slug="rust", label="Rust", category="language")
    db_session.add_all([m, s])
    await db_session.flush()
    g = SkillGap(
        user_id=u.id, scope="job", job_match_id=m.id, skill_id=s.id,
        skill_slug="rust", skill_label="Rust", severity="important",
    )
    db_session.add(g)
    await db_session.flush()
    assert g.status == "open" and g.frequency == 1
    g.severity = "bogus"
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 2: Run it — expect import failure.** `"$UV" run pytest tests/models/test_match_model.py -q` → `ModuleNotFoundError: app.models.match`.

- [ ] **Step 3: Write `backend/app/models/match.py`**

```python
from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_DIMENSIONS = (
    "dimension in ('skill','experience','education','project','technology',"
    "'location','role','seniority','salary','semantic')"
)


class JobMatch(Base, TimestampMixin):
    __tablename__ = "job_matches"
    __table_args__ = (
        CheckConstraint(
            "band is null or band in ('strong','good','partial','weak')",
            name="job_matches_band_valid",
        ),
        CheckConstraint(
            "status in ('scoring','ready','failed')", name="job_matches_status_valid"
        ),
        Index(
            "uq_job_matches_profile",
            "user_id", "job_id", "scorer_version",
            unique=True,
            postgresql_where=text("resume_version_id IS NULL"),
        ),
        Index("ix_job_matches_user_score", "user_id", text("score DESC")),
        Index("ix_job_matches_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK: `resume_versions` is a Phase 8 table. NULL = matched vs. the
    # user's current CareerProfile.
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[decimal.Decimal | None] = mapped_column(Numeric(5, 2))
    band: Mapped[str | None] = mapped_column(String(16))
    dimension_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    strengths: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    gaps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    explanation: Mapped[str | None] = mapped_column(Text)
    explanation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    inputs_hash: Mapped[str | None] = mapped_column(String(64))
    scorer_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'scoring'")
    )
    error: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[dt.datetime | None] = mapped_column()


class MatchComponent(Base, TimestampMixin):
    __tablename__ = "match_components"
    __table_args__ = (
        CheckConstraint(_DIMENSIONS, name="match_components_dimension_valid"),
        UniqueConstraint("job_match_id", "dimension", name="uq_match_components_dimension"),
        Index("ix_match_components_match", "job_match_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_matches.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_score: Mapped[decimal.Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    weight: Mapped[decimal.Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    contribution: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class SkillGap(Base, TimestampMixin):
    __tablename__ = "skill_gaps"
    __table_args__ = (
        CheckConstraint("scope in ('job','aggregate')", name="skill_gaps_scope_valid"),
        CheckConstraint(
            "severity in ('critical','important','nice_to_have')",
            name="skill_gaps_severity_valid",
        ),
        CheckConstraint(
            "status in ('open','learning','closed')", name="skill_gaps_status_valid"
        ),
        UniqueConstraint("job_match_id", "skill_id", name="uq_skill_gaps_job_skill"),
        Index("ix_skill_gaps_user_scope", "user_id", "scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(12), nullable=False)
    job_match_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_matches.id", ondelete="CASCADE")
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    skill_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_label: Mapped[str] = mapped_column(String(160), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'open'")
    )
    # No FK: `roadmaps` is a Phase 12 table.
    addressed_by_roadmap_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
```

- [ ] **Step 4: Write `backend/alembic/versions/0008_matches.py`** — model the file on `backend/alembic/versions/0007_jobs.py` (module vars `revision`/`down_revision`, `_TS = sa.TIMESTAMP(timezone=True)`, `_NOW = sa.text("now()")`, `pg.JSONB`, `pg.UUID(as_uuid=True)`, `op.create_index(..., postgresql_where=...)`, the `CREATE TRIGGER ... set_updated_at()` `op.execute` calls). `revision = "0008_matches"`, `down_revision = "0007_jobs"`. Create the three tables with the exact columns / server_defaults / CHECK names / indexes from the model above. Full `downgrade()`:

```python
def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_skill_gaps_set_updated_at ON skill_gaps")
    op.drop_table("skill_gaps")
    op.execute("DROP TRIGGER IF EXISTS trg_match_components_set_updated_at ON match_components")
    op.drop_table("match_components")
    op.execute("DROP TRIGGER IF EXISTS trg_job_matches_set_updated_at ON job_matches")
    op.drop_table("job_matches")
```

- [ ] **Step 5: Register the model** — in `backend/app/models/__init__.py` add `from app.models import match as match` between the `job` and `profile` lines.

- [ ] **Step 6: Run gates**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only 2>&1 | tail -3`
Expected: ruff/mypy/lint-imports clean (`Contracts: 2 kept, 0 broken`); collection error-free (~211 → ~214). The 3 model tests need Postgres — pass locally if a DB is available, else note CI-deferred.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/0008_matches.py backend/app/models/match.py backend/app/models/__init__.py backend/tests/models/test_match_model.py
git commit -m "feat(matching): job_matches + match_components + skill_gaps tables (migration 0008)"
```

---

## Task 2: `weights.py` + `scorer.py` (the deterministic scorer)

**Files:**
- Create: `backend/app/domain/matching/__init__.py` (empty)
- Create: `backend/app/domain/matching/weights.py`
- Create: `backend/app/domain/matching/scorer.py`
- Test: `backend/tests/domain/matching/test_weights.py`
- Test: `backend/tests/domain/matching/test_scorer.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure module).
- Produces — `weights.py`:
  - `SCORER_VERSION = "v1"`.
  - `WEIGHTS: dict[str, float]` — exactly these keys/values (sum = `1.0`):
    ```python
    WEIGHTS = {
        "skill": 0.22, "experience": 0.16, "technology": 0.13, "semantic": 0.12,
        "role": 0.10, "seniority": 0.08, "project": 0.07, "education": 0.05,
        "location": 0.04, "salary": 0.03,
    }
    ```
  - `BANDS: tuple[tuple[float, str], ...] = ((80.0, "strong"), (65.0, "good"), (45.0, "partial"), (0.0, "weak"))`.
  - `SENIORITY_LADDER: dict[str, int] = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "staff": 4, "principal": 5, "lead": 4, "manager": 4}` — `lead`/`manager` sit alongside `staff` (spec's profile ladder has no `intern`/`manager`; job ladder has both — this maps every value onto a 0–5 line).
  - `def band_for(score: float) -> str` — first `name` whose `threshold <= score`.
- Produces — `scorer.py`:
  - `@dataclass(frozen=True) class ProfileSnapshot`: `skill_ids: frozenset[str]` (stringified skill uuids), `skill_labels: tuple[str, ...]`, `tech: frozenset[str]` (lower-cased tech tokens from experiences + projects), `titles: tuple[str, ...]` (experience titles, lower-cased), `project_tech: frozenset[str]`, `has_degree: bool`, `fields: tuple[str, ...]` (education fields lower-cased), `seniority: str | None`, `years_experience: float | None`, `preferred_roles: tuple[str, ...]` (lower-cased), `locations: tuple[str, ...]` (lower-cased — profile location + preferred_locations), `work_modes: frozenset[str]`, `salary_min: int | None`, `summary_text: str`.
  - `@dataclass(frozen=True) class JobSnapshot`: `required: tuple[tuple[str, float], ...]` (`(skill_id_str, weight)` pairs from `job.required_skills`), `preferred: tuple[tuple[str, float], ...]`, `skill_labels: tuple[str, ...]` (all required+preferred labels lower-cased), `title: str` (lower-cased), `seniority: str | None`, `exp_min: int | None`, `exp_max: int | None`, `location: str | None` (lower-cased), `work_mode: str | None`, `salary_min: int | None`, `salary_max: int | None`, `chunk_embeddings: tuple[tuple[float, ...], ...]`.
  - `@dataclass(frozen=True) class Component`: `dimension: str`, `raw_score: float` (0–1, rounded to 3 dp), `weight: float`, `contribution: float` (rounded to 2 dp), `detail: dict[str, Any]`, `evidence: list[dict[str, Any]]`.
  - `@dataclass(frozen=True) class ScoreResult`: `score: float` (0–100, 2 dp), `band: str`, `components: tuple[Component, ...]` (always all 10, dimension order = `WEIGHTS` insertion order), `dimension_scores: dict[str, float]` (`{dimension: raw_score}`), `strengths: list[dict[str, Any]]`, `gaps: list[dict[str, Any]]`, `inputs_hash: str`.
  - `def score(profile: ProfileSnapshot, job: JobSnapshot, *, profile_embedding: tuple[float, ...] | None = None) -> ScoreResult`.
  - `def inputs_hash(profile: ProfileSnapshot, job: JobSnapshot) -> str` — `hashlib.sha256` hex of `json.dumps({...canonical fields...}, sort_keys=True, default=str)` including `SCORER_VERSION`. `profile_embedding` is **not** part of the hash (it is derived from `summary_text`, which is).

  **Dimension formulas** (each returns `(raw_score: float in [0,1], detail: dict, evidence: list)`):
  - **`skill`**: `covered = sum(w for sid, w in job.required if sid in profile.skill_ids)`; `total = sum(w for _, w in job.required) or 1.0`; `pref_bonus = 0.3 * (count of job.preferred sids in profile.skill_ids) / (len(job.preferred) or 1)`; `raw = min(1.0, covered / total + pref_bonus)` when `job.required` else (`1.0` if no required and no preferred, else `0.3 * pref_covered_frac`). `detail = {"matched": [sid for sid,_ in job.required if sid in profile.skill_ids], "missing": [sid for sid,w in job.required if sid not in profile.skill_ids]}`. `evidence = [{"kind": "profile_skill", "ref_id": sid, "snippet": ""} for sid in matched]`.
  - **`experience`**: years part — if `job.exp_min is None` → `1.0`; elif `profile.years_experience is None` → `0.5`; elif `profile.years_experience >= job.exp_min` → `1.0`; else `max(0.0, profile.years_experience / job.exp_min)`. title part — max Jaccard token overlap between `job.title` tokens and any `profile.titles` entry's tokens (0 if `profile.titles` empty). `raw = 0.6 * years_part + 0.4 * title_part`. `detail = {"years_part": ..., "title_part": ..., "job_exp_min": job.exp_min, "profile_years": profile.years_experience}`.
  - **`technology`**: `job_toks = set of word tokens across job.skill_labels`; `prof_toks = profile.tech`; `raw = len(job_toks & prof_toks) / (len(job_toks) or 1)`. `detail = {"overlap": sorted(job_toks & prof_toks), "job_only": sorted(job_toks - prof_toks)}`.
  - **`semantic`**: if `profile_embedding is None or not job.chunk_embeddings` → `raw = 0.5`, `detail = {"reason": "no embeddings"}`. else `mean_vec = elementwise mean of job.chunk_embeddings`; `raw = max(0.0, min(1.0, cosine(profile_embedding, mean_vec)))` where `cosine = dot / (norm_a * norm_b or 1)`. `detail = {"chunks": len(job.chunk_embeddings)}`.
  - **`role`**: if `not profile.preferred_roles` → `0.5`. else max Jaccard token overlap between `job.title` tokens and any preferred-role tokens. `detail = {"job_title": job.title, "preferred_roles": list(profile.preferred_roles)}`.
  - **`seniority`**: if `job.seniority is None or profile.seniority is None` → `0.5`. else `pj = SENIORITY_LADDER.get(job.seniority, 2)`, `pp = SENIORITY_LADDER.get(profile.seniority, 2)`; `raw = max(0.0, 1.0 - abs(pj - pp) / 5.0)`. `detail = {"job": job.seniority, "profile": profile.seniority}`.
  - **`project`**: if `not job.skill_labels` → `0.5`. `job_toks` (as technology). `raw = 1.0` if `profile.project_tech & job_toks` else (`0.4` if `profile.project_tech` else `0.0`). `detail = {"project_tech_overlap": sorted(profile.project_tech & job_toks)}`.
  - **`education`**: `raw = 0.6` if `profile.has_degree` else `0.2`; `+ 0.4` if any `profile.fields` token appears in `job.title` tokens (cap 1.0). `detail = {"has_degree": profile.has_degree}`.
  - **`location`**: if `job.work_mode == "remote"` → `1.0`. elif `job.work_mode and job.work_mode in profile.work_modes` → `1.0`. elif `job.location and any(loc and (loc in job.location or job.location in loc) for loc in profile.locations)` → `1.0`. elif `not job.work_mode and not job.location` → `0.5`. else `0.3`. `detail = {"job_work_mode": job.work_mode, "job_location": job.location, "profile_work_modes": sorted(profile.work_modes)}`.
  - **`salary`**: if `profile.salary_min is None or (job.salary_min is None and job.salary_max is None)` → `0.5`. `job_top = job.salary_max or job.salary_min`; if `job_top >= profile.salary_min` → `1.0`; else `max(0.0, job_top / profile.salary_min)`. `detail = {"job_max": job.salary_max, "job_min": job.salary_min, "profile_min": profile.salary_min}`.

  **Aggregation**: for each dim in `WEIGHTS` order build `Component(dimension, raw_score=round(raw, 3), weight=WEIGHTS[dim], contribution=round(raw * WEIGHTS[dim] * 100, 2), detail, evidence)`. `score = round(sum(c.contribution for c in components), 2)`. `band = band_for(score)`. `dimension_scores = {c.dimension: c.raw_score for c in components}`. `strengths = [{"dimension": c.dimension, "raw_score": c.raw_score, "contribution": c.contribution} for c in components if c.raw_score >= 0.7]` sorted by `contribution` desc, first 3. `gaps = [{"dimension": c.dimension, "raw_score": c.raw_score, "weight": c.weight} for c in components if c.raw_score < 0.5]` sorted by `weight` desc, first 4.

- [ ] **Step 1: Write `backend/tests/domain/matching/test_weights.py`**

```python
from app.domain.matching.weights import BANDS, SENIORITY_LADDER, WEIGHTS, band_for


def test_weights_sum_to_one_and_cover_ten_dimensions():
    assert set(WEIGHTS) == {
        "skill", "experience", "education", "project", "technology",
        "location", "role", "seniority", "salary", "semantic",
    }
    assert round(sum(WEIGHTS.values()), 10) == 1.0


def test_bands_thresholds():
    assert band_for(92.0) == "strong"
    assert band_for(80.0) == "strong"
    assert band_for(70.0) == "good"
    assert band_for(50.0) == "partial"
    assert band_for(10.0) == "weak"
    assert BANDS[0] == (80.0, "strong")


def test_seniority_ladder_maps_every_job_and_profile_value():
    for v in ("intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager"):
        assert v in SENIORITY_LADDER
    assert 0 <= min(SENIORITY_LADDER.values()) and max(SENIORITY_LADDER.values()) <= 5
```

- [ ] **Step 2: Write `backend/tests/domain/matching/test_scorer.py`** — one focused test per dimension plus aggregation, bands, determinism, and the hash. Skeleton (fill every assertion):

```python
from app.domain.matching.scorer import (
    JobSnapshot, ProfileSnapshot, inputs_hash, score,
)


def _profile(**kw) -> ProfileSnapshot:
    base = dict(
        skill_ids=frozenset(), skill_labels=(), tech=frozenset(), titles=(),
        project_tech=frozenset(), has_degree=False, fields=(), seniority=None,
        years_experience=None, preferred_roles=(), locations=(), work_modes=frozenset(),
        salary_min=None, summary_text="",
    )
    base.update(kw)
    return ProfileSnapshot(**base)


def _job(**kw) -> JobSnapshot:
    base = dict(
        required=(), preferred=(), skill_labels=(), title="", seniority=None,
        exp_min=None, exp_max=None, location=None, work_mode=None,
        salary_min=None, salary_max=None, chunk_embeddings=(),
    )
    base.update(kw)
    return JobSnapshot(**base)


def test_skill_dimension_weighted_coverage():
    p = _profile(skill_ids=frozenset({"a", "b"}))
    j = _job(required=(("a", 1.0), ("b", 1.0), ("c", 1.0)))
    r = score(p, j)
    skill = next(c for c in r.components if c.dimension == "skill")
    assert abs(skill.raw_score - 2 / 3) < 1e-6
    assert skill.detail["missing"] == ["c"]


def test_semantic_neutral_without_embeddings_then_cosine():
    r0 = score(_profile(), _job())
    assert next(c for c in r0.components if c.dimension == "semantic").raw_score == 0.5
    vec = tuple(1.0 if i == 0 else 0.0 for i in range(8))
    r1 = score(_profile(summary_text="x"), _job(chunk_embeddings=(vec,)), profile_embedding=vec)
    assert next(c for c in r1.components if c.dimension == "semantic").raw_score == 1.0


def test_seniority_ordinal_distance():
    r = score(_profile(seniority="junior"), _job(seniority="staff"))
    sr = next(c for c in r.components if c.dimension == "seniority").raw_score
    assert abs(sr - (1 - 3 / 5)) < 1e-6


def test_aggregation_score_band_and_strengths():
    p = _profile(
        skill_ids=frozenset({"a"}), seniority="senior", years_experience=6.0,
        work_modes=frozenset({"remote"}), has_degree=True, preferred_roles=("ml engineer",),
        tech=frozenset({"python", "pytorch"}), project_tech=frozenset({"python"}),
    )
    j = _job(
        required=(("a", 1.0),), skill_labels=("python", "pytorch"), title="ml engineer",
        seniority="senior", exp_min=5, work_mode="remote",
    )
    r = score(p, j)
    assert 0 <= r.score <= 100
    assert r.band in {"strong", "good", "partial", "weak"}
    assert abs(r.score - sum(c.contribution for c in r.components)) < 0.01
    assert {c.dimension for c in r.components} == set(r.dimension_scores)
    assert all(s["raw_score"] >= 0.7 for s in r.strengths)


def test_score_is_deterministic_and_hash_stable():
    p, j = _profile(skill_ids=frozenset({"a"})), _job(required=(("a", 1.0),))
    assert score(p, j) == score(p, j)
    h1 = inputs_hash(p, j)
    assert h1 == inputs_hash(p, j)
    assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)
    # summary_text is part of the hash; a different profile summary → different hash
    assert inputs_hash(_profile(summary_text="a"), j) != inputs_hash(_profile(summary_text="b"), j)
```

- [ ] **Step 3: Run — expect import failure.**
- [ ] **Step 4: Implement `weights.py` then `scorer.py`** per the Interfaces block. Keep `scorer.py` free of any `import` beyond `hashlib`, `json`, `math`, `dataclasses`, `typing`. A private `_tokens(s: str) -> set[str]` = `set(re.findall(r"[a-z0-9+#.]+", s.lower()))` — put `import re` at the top (allowed).
- [ ] **Step 5: Run** both test files → all green. `ruff` / `mypy` / `lint-imports` → clean.
- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/matching/__init__.py backend/app/domain/matching/weights.py backend/app/domain/matching/scorer.py backend/tests/domain/matching/test_weights.py backend/tests/domain/matching/test_scorer.py
git commit -m "feat(matching): deterministic 10-dimension MatchScorer + weights"
```

---

## Task 3: `explainer.py` + `gaps.py`

**Files:**
- Create: `backend/app/domain/matching/gaps.py`
- Create: `backend/app/domain/matching/explainer.py`
- Test: `backend/tests/domain/matching/test_gaps.py`
- Test: `backend/tests/domain/matching/test_explainer.py`

**Interfaces:**
- Consumes: `Component`, `ScoreResult`, `ProfileSnapshot`, `JobSnapshot` (Task 2); `LLMProvider`, `LLMMessage`, `LLMResult` (`app.domain.llm.provider`); `AppError` (`app.core.errors`).
- Produces — `gaps.py`:
  - `@dataclass(frozen=True) class GapDraft`: `skill_id: str`, `slug: str`, `label: str`, `severity: str` (`critical`/`important`/`nice_to_have`).
  - `def derive_gaps(job_required: list[dict[str, Any]], job_preferred: list[dict[str, Any]], skill_component: Component) -> list[GapDraft]` — `missing = set(skill_component.detail.get("missing", []))`; for each entry in `job_required` whose `skill_id` (str) is in `missing`: `severity = "critical" if entry["weight"] >= 0.7 else "important"`; for each `job_preferred` entry whose `skill_id` is in `missing`: `severity = "nice_to_have"`. De-dupe by `skill_id` (required wins). Returns list ordered `critical`, `important`, `nice_to_have` then by label.
- Produces — `explainer.py`:
  - `EXPLAIN_SYSTEM_PROMPT` (module const) — instructs: "You are handed a pre-computed match score and its component breakdown. Write 2–4 sentences, plain and specific, explaining why this candidate profile does or doesn't fit this role. Reference the strongest and weakest dimensions by name. NEVER state a numeric score, NEVER contradict the breakdown, NEVER invent facts not in the inputs."
  - `class NarrativeOut(BaseModel)`: `text: str`.
  - `class MatchExplainer`: `__init__(self, llm: LLMProvider, *, model: str)`, `last_usage: LLMResult | None`. `async def explain(self, *, job_title: str, company: str | None, result: ScoreResult) -> str | None` — builds a compact user message (band, top strengths, top gaps, dimension_scores), `llm.complete([system, user], schema=NarrativeOut, max_tokens=512)`; returns `result.structured["text"].strip() or None`; on `result.structured is None` or empty text → return `None` (never raise). Sets `last_usage`.
  - `RATIONALE_SYSTEM_PROMPT` — "For each listed skill, write ONE sentence on why it matters for this specific role. Return a JSON object mapping the exact skill label to its sentence. No score, no fluff."
  - `class RationalesOut(BaseModel)`: `rationales: dict[str, str] = Field(default_factory=dict)`.
  - `class GapRationaleWriter`: `__init__(self, llm, *, model)`, `last_usage`. `async def write(self, *, job_title: str, gaps: list[GapDraft]) -> dict[str, str]` — one call; user message lists `job_title` + the gap labels; returns `result.structured["rationales"]` filtered to `{label: text for label, text in ... if label in {g.label for g in gaps} and text.strip()}`; `{}` on failure (never raise).

- [ ] **Step 1: Write `backend/tests/domain/matching/test_gaps.py`**

```python
from app.domain.matching.gaps import GapDraft, derive_gaps
from app.domain.matching.scorer import Component


def _skill_component(missing: list[str]) -> Component:
    return Component(
        dimension="skill", raw_score=0.5, weight=0.22, contribution=11.0,
        detail={"matched": [], "missing": missing}, evidence=[],
    )


def test_derive_gaps_severity_from_weight_and_list():
    req = [
        {"skill_id": "a", "slug": "rust", "label": "Rust", "weight": 0.9},
        {"skill_id": "b", "slug": "go", "label": "Go", "weight": 0.4},
    ]
    pref = [{"skill_id": "c", "slug": "helm", "label": "Helm", "weight": 0.3}]
    gaps = derive_gaps(req, pref, _skill_component(["a", "b", "c"]))
    assert [(g.slug, g.severity) for g in gaps] == [
        ("rust", "critical"), ("go", "important"), ("helm", "nice_to_have")
    ]


def test_derive_gaps_dedups_required_over_preferred_and_skips_covered():
    req = [{"skill_id": "a", "slug": "rust", "label": "Rust", "weight": 0.9}]
    pref = [{"skill_id": "a", "slug": "rust", "label": "Rust", "weight": 0.2}]
    assert [g.severity for g in derive_gaps(req, pref, _skill_component(["a"]))] == ["critical"]
    assert derive_gaps(req, pref, _skill_component([])) == []
```

- [ ] **Step 2: Write `backend/tests/domain/matching/test_explainer.py`** (fake LLM; mirrors `tests/domain/jobs/test_extractor.py`): `MatchExplainer(FakeLLMProvider(), model="fake").explain(...)` → the fake stubs `NarrativeOut.text` to `""` → returns `None`; a canned subclass returning `{"text": "Strong on skills, weak on seniority."}` → returns that string. `GapRationaleWriter(FakeLLMProvider()).write(...)` → `{}`; a canned subclass returning `{"rationales": {"Rust": "Core to the serving layer."}}` with a matching gap label → `{"Rust": "Core to the serving layer."}`.

- [ ] **Step 3: Run — expect import failure.**
- [ ] **Step 4: Implement `gaps.py` then `explainer.py`.**
- [ ] **Step 5: Run** both test files → green. `ruff` / `mypy` / `lint-imports` → clean.
- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/matching/gaps.py backend/app/domain/matching/explainer.py backend/tests/domain/matching/test_gaps.py backend/tests/domain/matching/test_explainer.py
git commit -m "feat(matching): gap derivation + LLM narrative/rationale (prose only, non-fatal)"
```

---

## Task 4: `MatchService`

**Files:**
- Create: `backend/app/domain/matching/service.py`
- Modify: `backend/tests/conftest.py` (extend `_no_enqueue`)
- Test: `backend/tests/domain/matching/test_service.py`

**Interfaces:**
- Consumes: `JobMatch`, `MatchComponent`, `SkillGap` (Task 1); `ProfileSnapshot`, `JobSnapshot`, `ScoreResult`, `Component`, `score`, `inputs_hash` (Task 2); `GapDraft`, `derive_gaps` (Task 3); `SCORER_VERSION` (Task 2); `CareerProfile`, `ProfileSkill`, `ProfileExperience`, `ProfileProject`, `ProfileEducation` (`app.models.profile`); `Skill` (`app.models.skill`); `Job`, `JobChunk` (`app.models.job`); `enqueue` (`app.core.queue`); `audit` (`app.core.audit`); `NotFoundError` (`app.core.errors`); `current_request_id` (`app.core.logging`).
- Produces — `class MatchService`:
  - `__init__(self, session: AsyncSession, *, settings: Settings | None = None)`.
  - `async def build_profile_snapshot(self, user_id: uuid.UUID) -> ProfileSnapshot` — reads `CareerProfile` (or a defaults snapshot if none), `profile_skills` joined to `skills` (skill_ids as `str`, labels), experiences + projects (`tech[]`, titles), education (`degree`/`field`). `summary_text` = `" • ".join([*preferred_roles, *skill_labels[:30], *titles, *project_names])[:2000]`.
  - `async def build_job_snapshot(self, job_id: uuid.UUID) -> JobSnapshot` — reads `Job` (`required_skills`/`preferred_skills` → `(str(s["skill_id"]), float(s["weight"]))` pairs; labels), `job_chunks.embedding` (skip NULLs → `tuple(tuple(float(x) for x in vec) ...)`). Raises `NotFoundError` if the job is missing.
  - `async def get_or_create(self, user_id: uuid.UUID, job_id: uuid.UUID) -> JobMatch` — finds the `resume_version_id IS NULL` row for `(user_id, job_id, SCORER_VERSION)`. If it exists and `status == "ready"` → return it. If it exists and `status in ("scoring","failed")` → re-enqueue (`_job_id` dedups) and return it. If none → insert `JobMatch(user_id, job_id, scorer_version=SCORER_VERSION, status="scoring")`, flush, `enqueue("score_match", str(m.id), _defer_by=2.0, _job_id=f"score_match:{m.id}")`, `_audit("match.request", ...)`, return it.
  - `async def apply_score(self, job_match_id: uuid.UUID, *, result: ScoreResult, gaps: list[GapDraft], explanation: str | None, explanation_meta: dict, rationales: dict[str, str]) -> None` — worker callback. Loads the `JobMatch` (any). Writes `score`, `band`, `dimension_scores`, `strengths`, `gaps` (`result.gaps`), `explanation`, `explanation_meta`, `inputs_hash=result.inputs_hash`, `status="ready"`, `error=None`, `computed_at=now(UTC)`. `DELETE FROM match_components WHERE job_match_id=:id` then insert one row per `result.components` (Decimal-cast the numerics). `DELETE FROM skill_gaps WHERE job_match_id=:id` then insert one `SkillGap` per `GapDraft` (`scope="job"`, `user_id` from the match, `rationale=rationales.get(draft.label)`). `flush`.
  - `async def mark_failed(self, job_match_id: uuid.UUID, error: str) -> None` — `status="failed"`, `error=error[:500]`, `flush`.
  - `async def get(self, user_id: uuid.UUID, match_id: uuid.UUID) -> JobMatch` — by id, `user_id` guard, `NotFoundError`.
  - `async def list_for_user(self, user_id, *, job_id: uuid.UUID | None, min_score: float | None, sort: str) -> list[JobMatch]` — `resume_version_id IS NULL`, optional `job_id`, `score >= min_score`, `order_by score DESC` (default) or `computed_at DESC` when `sort == "recent"`.
  - `async def components(self, user_id, match_id) -> list[MatchComponent]` — after a `get` ownership check, `order_by contribution DESC`.
  - `async def recompute(self, user_id: uuid.UUID, *, scope: str, job_id: uuid.UUID | None) -> int` — `scope == "all"`: select every visible `status="ready"` job (`Job.user_id == user_id OR Job.user_id IS NULL`, `deleted_at IS NULL`). For each: `m = await self.get_or_create(user_id, job.id)` (inserts a `scoring` row when absent), then if `m.status == "ready"` set `m.status = "scoring"`, then `await enqueue("score_match", str(m.id), _defer_by=2.0, _job_id=f"score_match:{m.id}")` **unconditionally** (the `_job_id` dedups a still-queued run; the worker's own `inputs_hash` guard makes a re-run a no-op when nothing changed). `flush`. Return the job count. `scope != "all"` → `job_id` is the parsed uuid → the same one-job path. `_audit("match.recompute", user_id, meta={"scope": scope, "count": n})`.
  - `async def job_scores_for(self, user_id: uuid.UUID, job_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[float | None, str | None, str]]` — one query: `select(JobMatch.job_id, JobMatch.score, JobMatch.band, JobMatch.status).where(JobMatch.user_id == user_id, JobMatch.resume_version_id.is_(None), JobMatch.scorer_version == SCORER_VERSION, JobMatch.job_id.in_(job_ids))` → `{job_id: (float(score) if score else None, band, status)}`.

- [ ] **Step 1: Extend conftest** — in `backend/tests/conftest.py`, add to `_no_enqueue`: `monkeypatch.setattr("app.domain.matching.service.enqueue", _noop, raising=False)`.

- [ ] **Step 2: Write `backend/tests/domain/matching/test_service.py`** (DB). Cover: `build_profile_snapshot` reads skills+experiences (seed a `CareerProfile` + `profile_skills` + `ProfileExperience`); `build_job_snapshot` reads a job's required-skill pairs + chunk embeddings; `get_or_create` inserts a `scoring` row + enqueues (spy), and a second call returns the same row; `apply_score` writes the match + 10 components + N skill_gaps and flips `status="ready"`; `job_scores_for` returns `{job_id: (score, band, status)}`.

```python
import decimal
import uuid

import pytest

from app.domain.matching.gaps import GapDraft
from app.domain.matching.scorer import ScoreResult, score, JobSnapshot, ProfileSnapshot
from app.domain.matching.service import MatchService
from app.domain.matching.weights import SCORER_VERSION
from app.models.job import Job, JobChunk
from app.models.match import JobMatch, MatchComponent, SkillGap
from app.models.profile import CareerProfile, ProfileExperience
from app.models.skill import ProfileSkill, Skill
from app.models.user import User


async def _seed(db_session, email="ms@x.com"):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u); await db_session.flush()
    p = CareerProfile(user_id=u.id, seniority="senior", years_experience=decimal.Decimal("6"))
    s = Skill(slug="python", label="Python", category="language")
    db_session.add_all([p, s]); await db_session.flush()
    db_session.add(ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id, source="user"))
    db_session.add(ProfileExperience(user_id=u.id, profile_id=p.id, company="A", title="ML Engineer",
                                     source="user", order_index=0, tech=["Python"]))
    j = Job(user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
            title="Senior ML Engineer",
            required_skills=[{"skill_id": str(s.id), "slug": "python", "label": "Python", "weight": 0.9}],
            preferred_skills=[])
    db_session.add(j); await db_session.flush()
    db_session.add(JobChunk(job_id=j.id, chunk_index=0, section="description", content="c",
                            token_count=1, embed_model="fake-embed-1", embed_dim=1024,
                            embedding=[0.1] * 1024))
    await db_session.flush()
    return u, p, s, j


async def test_build_snapshots(db_session):
    u, p, s, j = await _seed(db_session)
    svc = MatchService(db_session)
    ps = await svc.build_profile_snapshot(u.id)
    assert str(s.id) in ps.skill_ids and ps.seniority == "senior"
    js = await svc.build_job_snapshot(j.id)
    assert js.required and js.required[0][0] == str(s.id)
    assert len(js.chunk_embeddings) == 1


async def test_get_or_create_inserts_scoring_and_enqueues(db_session, monkeypatch):
    calls: list[str] = []
    async def _spy(task, *a, **k):
        calls.append(task); return "x"
    monkeypatch.setattr("app.domain.matching.service.enqueue", _spy)
    u, p, s, j = await _seed(db_session, "ms2@x.com")
    m = await MatchService(db_session).get_or_create(u.id, j.id)
    assert m.status == "scoring" and m.scorer_version == SCORER_VERSION
    assert calls == ["score_match"]
    again = await MatchService(db_session).get_or_create(u.id, j.id)
    assert again.id == m.id


async def test_apply_score_writes_components_and_gaps(db_session):
    u, p, s, j = await _seed(db_session, "ms3@x.com")
    svc = MatchService(db_session)
    m = await svc.get_or_create(u.id, j.id)
    ps = await svc.build_profile_snapshot(u.id)
    js = await svc.build_job_snapshot(j.id)
    result = score(ps, js)
    gap = GapDraft(skill_id=str(uuid.uuid4()), slug="rust", label="Rust", severity="critical")
    # a real gap needs a real skill row for the FK
    rust = Skill(slug="rust", label="Rust", category="language")
    db_session.add(rust); await db_session.flush()
    gap = GapDraft(skill_id=str(rust.id), slug="rust", label="Rust", severity="critical")
    await svc.apply_score(m.id, result=result, gaps=[gap], explanation="ok",
                          explanation_meta={"model": "fake"}, rationales={"Rust": "Needed."})
    await db_session.refresh(m)
    assert m.status == "ready" and m.score is not None and m.band is not None
    comps = (await db_session.execute(
        __import__("sqlalchemy").select(MatchComponent).where(MatchComponent.job_match_id == m.id)
    )).scalars().all()
    assert len(comps) == 10
    sg = (await db_session.execute(
        __import__("sqlalchemy").select(SkillGap).where(SkillGap.job_match_id == m.id)
    )).scalars().all()
    assert len(sg) == 1 and sg[0].rationale == "Needed."


async def test_job_scores_for(db_session):
    u, p, s, j = await _seed(db_session, "ms4@x.com")
    svc = MatchService(db_session)
    m = await svc.get_or_create(u.id, j.id)
    m.score = decimal.Decimal("92.00"); m.band = "strong"; m.status = "ready"
    await db_session.flush()
    scores = await svc.job_scores_for(u.id, [j.id])
    assert scores[j.id] == (92.0, "strong", "ready")
```

(Replace the `__import__("sqlalchemy").select` hacks with a top-level `from sqlalchemy import select` in the real file — Ruling-style cleanup, keep assertions identical.)

- [ ] **Step 3: Run — expect failure. Step 4: Implement `service.py`.** Model the audit helper, session use, `_visible`-style filter on `recompute` after `app/domain/jobs/service.py`. **Step 5: Run** `tests/domain/matching/test_service.py` (DB) → PASS or `--collect-only` clean + CI-deferred; `ruff`/`mypy`/`lint-imports` clean.
- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/matching/service.py backend/tests/conftest.py backend/tests/domain/matching/test_service.py
git commit -m "feat(matching): MatchService — snapshots, get_or_create, apply_score, recompute, job_scores_for"
```

---

## Task 5: `score_match` worker task

**Files:**
- Create: `backend/app/worker/tasks/matching.py`
- Modify: `backend/app/worker/tasks/__init__.py`
- Modify: `backend/app/worker/main.py`
- Test: `backend/tests/worker/test_matching_task.py`

**Interfaces:**
- Consumes: `MatchService` (Task 4); `score`, `inputs_hash` (Task 2); `derive_gaps` (Task 3); `MatchExplainer`, `GapRationaleWriter` (Task 3); `get_llm_provider`, `get_embeddings_provider`; `record_failure`; `MAX_TRIES` from `app.worker.tasks.resume`; `JobMatch` (`app.models.match`).
- Produces — `app/worker/tasks/matching.py`: `__all__ = ["score_match"]`; a **verbatim `_session_for` copy** from `app/worker/tasks/jobs.py`; `log = get_logger("worker.score_match")`; `async def score_match(ctx: dict[str, Any], job_match_id: str) -> dict[str, Any]`:
  1. `async with _session_for() as session:` — `m = await session.get(JobMatch, uuid.UUID(job_match_id))`; if `None` → `record_failure` + `return {"job_match_id": job_match_id, "status": "missing"}`; if `m.status == "ready"` and `m.inputs_hash` matches the freshly computed hash → `return {"status": "skipped"}` (idempotent re-run guard — compute the snapshots + `inputs_hash` first to check).
  2. `try:` — `svc = MatchService(session, settings=settings)`; `profile = await svc.build_profile_snapshot(m.user_id)`; `job = await svc.build_job_snapshot(m.job_id)`; `emb = await get_embeddings_provider(settings).embed_query(profile.summary_text) if profile.summary_text else None`; `result = score(profile, job, profile_embedding=tuple(emb) if emb else None)`.
  3. `skill_comp = next(c for c in result.components if c.dimension == "skill")`; load the `Job` row's `required_skills`/`preferred_skills` (via `svc` or a direct `session.get(Job, m.job_id)`); `drafts = derive_gaps(job_row.required_skills, job_row.preferred_skills, skill_comp)`.
  4. `explainer = MatchExplainer(get_llm_provider(settings), model=settings.llm_model_extraction)`; `narrative = await explainer.explain(job_title=..., company=..., result=result)` (returns `None` on failure — **do not** wrap in try, it never raises); `expl_meta = {"model": explainer.last_usage.model if explainer.last_usage else "unknown"}`.
  5. `rationales = await GapRationaleWriter(get_llm_provider(settings), model=...).write(job_title=..., gaps=drafts)` (returns `{}` on failure).
  6. `await svc.apply_score(m.id, result=result, gaps=drafts, explanation=narrative, explanation_meta=expl_meta, rationales=rationales)`; `await session.commit()`; `log.info("match_scored", job_match_id=job_match_id, score=result.score, band=result.band, gaps=len(drafts))`; `return {"job_match_id": job_match_id, "status": "ready", "score": result.score}`.
  7. `except Exception as exc:` — `await session.rollback()`; `if ctx.get("job_try", 1) < MAX_TRIES: raise`; re-load `m`; `if m is not None: await MatchService(session).mark_failed(m.id, "We couldn't score this job."); await session.commit()`; `await record_failure("score_match", args=(job_match_id,), kwargs={}, error=exc)`; `raise`.
- `worker/tasks/__init__.py`: `from app.worker.tasks.matching import score_match` + add `"score_match"` to `__all__`.
- `worker/main.py`: import `score_match` from `app.worker.tasks` and append to `WorkerSettings.functions`.

- [ ] **Step 1: Write `backend/tests/worker/test_matching_task.py`** (DB). Monkeypatch `app.worker.tasks.matching._session_for` to `_ctx(db_session)` (see `tests/worker/test_jobs_task.py`). Seed the same profile+job as Task 4's `_seed`, insert a `JobMatch(status="scoring")` via `MatchService.get_or_create`, run `await score_match({}, str(m.id))`, assert `m.status == "ready"`, `m.score` set, `m.band` set, 10 `match_components`, `m.dimension_scores` has 10 keys. A second test: `status="ready"` with the matching `inputs_hash` → `score_match` returns `{"status": "skipped"}`.

- [ ] **Step 2: Run — expect import failure. Step 3: add `job_channel`-free `_session_for` copy + the task. Step 4: register.** **Step 5: Run** `tests/worker/test_matching_task.py` (DB) → PASS or `--collect-only` clean + CI. `ruff`/`mypy`/`lint-imports` clean (confirm `Contracts: 2 kept`).
- [ ] **Step 6: Commit**

```bash
git add backend/app/worker/tasks/matching.py backend/app/worker/tasks/__init__.py backend/app/worker/main.py backend/tests/worker/test_matching_task.py
git commit -m "feat(matching): score_match worker task — scorer + non-fatal LLM prose"
```

---

## Task 6: `/matches` API + schemas

**Files:**
- Create: `backend/app/api/v1/schemas/matches.py`
- Create: `backend/app/api/v1/matches.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/core/rate_limit.py`
- Test: `backend/tests/api/test_matches.py`

**Interfaces:**
- Consumes: `MatchService` (Task 4); `CurrentUser`, `DbDep` (`app.api.deps`); `NotFoundError`, `ValidationAppError`.
- Produces — `schemas/matches.py`:
  - `MatchRefOut` — `id: uuid.UUID`, `status: str`.
  - `MatchDimOut` — `dimension: str`, `raw_score: float`, `weight: float`, `contribution: float`.
  - `MatchComponentOut(MatchDimOut)` — `detail: dict[str, Any]`, `evidence: list[dict[str, Any]]`.
  - `MatchOut` — `model_config = ConfigDict(from_attributes=True)` NOT used (map explicitly); `id`, `job_id`, `status: str`, `score: float | None`, `band: str | None`, `dimension_scores: dict[str, float]`, `strengths: list[dict[str, Any]]`, `gaps: list[dict[str, Any]]`, `explanation: str | None`, `computed_at: dt.datetime | None`.
  - `MatchListOut` — `items: list[MatchOut]`.
  - `RecomputeIn` — `extra="forbid"`; `scope: str = Field(pattern=r"^(all|[0-9a-fA-F-]{36})$")`.
  - `MatchCreateIn` — `extra="forbid"`; `job_id: uuid.UUID`.
- Produces — `matches.py` `router = APIRouter(prefix="/matches", tags=["matches"])`:
  - `POST ""` → 202, `MatchCreateIn` → `MatchService(db).get_or_create(user.id, body.job_id)` → `MatchRefOut`.
  - `GET ""` → `MatchListOut` — query `job_id: uuid.UUID | None`, `min_score: float | None`, `sort: str = "score"`; `_match_out(m)` mapper for each.
  - `GET "/{match_id}"` → `MatchOut` via `MatchService(db).get(user.id, match_id)` + `_match_out`.
  - `GET "/{match_id}/components"` → `list[MatchComponentOut]` via `MatchService(db).components(user.id, match_id)`.
  - `POST "/recompute"` → 202, `RecomputeIn` → `MatchService(db).recompute(user.id, scope="all" if body.scope=="all" else "job", job_id=None if body.scope=="all" else uuid.UUID(body.scope))` → `{"status": "queued", "count": n}`.
- `router.py`: `from app.api.v1 import ... matches, ...` (alpha) + `api_router.include_router(matches.router)` (before `profile`).
- `rate_limit.py` `_bucket`: after the résumé/jobs upload check, add `if method == "POST" and path in (f"{base}/matches", f"{base}/matches/recompute"): return "llm"`.

- [ ] **Step 1: Write `backend/tests/api/test_matches.py`** (DB+Redis, `client` + `_auth` from `tests/api/test_profile_skills.py`). Cover: `POST /matches {job_id}` for a seeded ready job → 202 `{id, status: "scoring"}`; `GET /matches/{id}` → the match shape (status `scoring`, `score` null before the worker runs); `GET /matches` with no job → a list; `POST /matches/recompute {scope: "all"}` → 202 `{status: "queued", count: >=0}`; `POST /matches {job_id: <random uuid>}` → 404 (job not found) — or 202 then the worker no-ops (assert whichever `MatchService.get_or_create` does: it should `build_job_snapshot` → `NotFoundError` → the route returns 404). **Decision: `get_or_create` validates the job exists (via `build_job_snapshot` or a `session.get`) and raises `NotFoundError` for an unknown job.**

- [ ] **Step 2: Run — expect failure. Step 3: implement schemas → `matches.py` → register → rate-limit.** **Step 4: Run** `tests/api/test_matches.py` (DB+Redis) → PASS or `--collect-only` + CI. `ruff`/`mypy`/`lint-imports` clean. `"$UV" run python -c "import os; [os.environ.setdefault(k,v) for k,v in {'DATABASE_URL':'postgresql+asyncpg://x','DATABASE_URL_TEST':'postgresql+asyncpg://x','REDIS_URL':'redis://x','JWT_SECRET':'x','EMBEDDINGS_PROVIDER':'fake','LLM_PROVIDER':'fake'}.items()]; from app.main import create_app; print(sorted(p for p in create_app().openapi()['paths'] if 'match' in p))"` → shows `/api/v1/matches`, `/api/v1/matches/{match_id}`, `/api/v1/matches/{match_id}/components`, `/api/v1/matches/recompute`.
- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/schemas/matches.py backend/app/api/v1/matches.py backend/app/api/v1/router.py backend/app/core/rate_limit.py backend/tests/api/test_matches.py
git commit -m "feat(matching): /matches API — create, list, detail, components, recompute"
```

---

## Task 7: `/skill-gaps` API + schemas

**Files:**
- Create: `backend/app/api/v1/schemas/skill_gaps.py`
- Create: `backend/app/api/v1/skill_gaps.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/domain/matching/service.py` (add gap read/patch helpers)
- Test: `backend/tests/api/test_skill_gaps.py`

**Interfaces:**
- Consumes: `MatchService` (Task 4); `SkillGap` (Task 1); `CurrentUser`, `DbDep`; `NotFoundError`.
- Produces — `MatchService` gains:
  - `async def list_skill_gaps(self, user_id: uuid.UUID, *, scope: str, job_match_id: uuid.UUID | None) -> list[SkillGap]` — `where(SkillGap.user_id == user_id, SkillGap.scope == scope)` + optional `job_match_id`, `order_by` a severity rank (`critical`<`important`<`nice_to_have`) then `skill_label`.
  - `async def set_gap_status(self, user_id: uuid.UUID, gap_id: uuid.UUID, status: str) -> SkillGap` — load `where(id == gap_id, user_id == user_id)` or `NotFoundError`; `gap.status = status`; `flush`; return.
- Produces — `schemas/skill_gaps.py`: `SkillGapOut` (`id`, `scope`, `job_match_id: uuid.UUID | None`, `skill_slug`, `skill_label`, `severity`, `frequency`, `rationale: str | None`, `status`), `SkillGapPatchIn` (`extra="forbid"`, `status: str = Field(pattern=r"^(open|learning|closed)$")`).
- Produces — `skill_gaps.py` `router = APIRouter(prefix="/skill-gaps", tags=["skill-gaps"])`:
  - `GET ""` → `list[SkillGapOut]` — query `scope: str = "job"`, `job_match_id: uuid.UUID | None = None`.
  - `PATCH "/{gap_id}"` → `SkillGapOut` — `SkillGapPatchIn` → `MatchService(db).set_gap_status(user.id, gap_id, body.status)`.
- `router.py`: `include_router(skill_gaps.router)` (alpha — after `resumes`? the router name is `skill_gaps`; put its `include_router` after `resumes`).

- [ ] **Step 1: Write `backend/tests/api/test_skill_gaps.py`** (DB). Seed a `JobMatch` + two `SkillGap` rows (one `critical`, one `nice_to_have`), `GET /skill-gaps?scope=job&job_match_id=<id>` → both, critical first; `PATCH /skill-gaps/{id} {status:"learning"}` → 200, status updated; `PATCH` a cross-user gap → 404.
- [ ] **Step 2–4:** run → fail → implement (`MatchService` helpers, schemas, router, register) → `"$UV" run pytest tests/api/test_skill_gaps.py -q` + `ruff`/`mypy`/`lint-imports` clean.
- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/schemas/skill_gaps.py backend/app/api/v1/skill_gaps.py backend/app/api/v1/router.py backend/app/domain/matching/service.py backend/tests/api/test_skill_gaps.py
git commit -m "feat(matching): /skill-gaps API — list + status patch"
```

---

## Task 8: Discovery wiring (match score on cards, has_match filter, sort=match)

**Files:**
- Modify: `backend/app/domain/jobs/service.py`
- Modify: `backend/app/api/v1/schemas/jobs.py`
- Modify: `backend/app/api/v1/jobs.py`
- Test: `backend/tests/api/test_jobs.py` (extend)

**Interfaces:**
- Consumes: `MatchService.job_scores_for` (Task 4); `JobMatch` (Task 1); `SCORER_VERSION` (Task 2).
- Produces:
  - `JobFilters` gains `has_match: bool = False`; `sort` now also accepts `"match"`.
  - `JobService._filtered` — when `f.has_match`: `stmt = stmt.where(exists().where(JobMatch.job_id == Job.id, JobMatch.user_id == user_id, JobMatch.resume_version_id.is_(None), JobMatch.scorer_version == SCORER_VERSION, JobMatch.status == "ready"))`.
  - `JobService.list_` — when `f.sort == "match"`: `LEFT JOIN` a correlated subquery / `join(JobMatch, and_(JobMatch.job_id == Job.id, JobMatch.user_id == user_id, JobMatch.resume_version_id.is_(None), JobMatch.scorer_version == SCORER_VERSION), isouter=True).order_by(JobMatch.score.desc().nulls_last(), Job.created_at.desc())`. Otherwise unchanged (`created_at DESC`). `total` subquery must strip the join+order (`stmt.order_by(None)` already covers order; the `EXISTS` in `_filtered` is fine inside the count subquery; the `sort=match` outer join is added only to the page query, not `_filtered`).
  - `JobCardOut` gains `match_score: float | None = None`, `match_band: str | None = None`, `match_status: str | None = None`.
  - `jobs.py` `_card(job, match=None)` — accept an optional `(score, band, status)` tuple, set the three fields. `list_jobs` — after `rows, total = await JobService(db).list_(...)`, call `scores = await MatchService(db).job_scores_for(user.id, [j.id for j in rows])`, `items=[_card(j, scores.get(j.id)) for j in rows]`. Add `has_match: bool = False` query param → `JobFilters(has_match=has_match, ...)`.
  - `get_job` — attach the caller's current match summary: `m = scores2.get(job.id)` via `MatchService(db).job_scores_for(user.id, [job.id])`; pass into `_detail`.

- [ ] **Step 1: Extend `backend/tests/api/test_jobs.py`** — a new test: seed a ready seed-job + a `JobMatch(status="ready", score=88, band="good")` for the auth'd user; `GET /jobs` → the card carries `match_score == 88.0`, `match_band == "good"`, `match_status == "ready"`; `GET /jobs?has_match=true` → includes it; seed a second job with no match → `?has_match=true` excludes it; `GET /jobs?sort=match` → the matched job sorts first.
- [ ] **Step 2–4:** run → fail → implement → `"$UV" run pytest tests/api/test_jobs.py -q` + full `--collect-only` clean + `ruff`/`mypy`/`lint-imports` clean.
- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/jobs/service.py backend/app/api/v1/schemas/jobs.py backend/app/api/v1/jobs.py backend/tests/api/test_jobs.py
git commit -m "feat(matching): discovery match badges + has_match filter + sort=match"
```

---

## Task 9: frontend — types + endpoints + query keys

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/api/endpoints.ts`
- Modify: `frontend/lib/query.ts`
- Test: `frontend/tests/api/endpoints.test.ts` (extend)

**Interfaces — Produces:**
- `types.ts`:
  ```ts
  export type MatchBand = "strong" | "good" | "partial" | "weak";
  export type MatchStatus = "scoring" | "ready" | "failed";
  export type SkillGapStatus = "open" | "learning" | "closed";
  export type MatchDimension =
    | "skill" | "experience" | "education" | "project" | "technology"
    | "location" | "role" | "seniority" | "salary" | "semantic";
  export interface MatchComponent {
    dimension: MatchDimension; raw_score: number; weight: number; contribution: number;
    detail: Record<string, unknown>; evidence: Record<string, unknown>[];
  }
  export interface JobMatch {
    id: string; job_id: string; status: MatchStatus;
    score: number | null; band: MatchBand | null;
    dimension_scores: Record<string, number>;
    strengths: { dimension: string; raw_score: number; contribution: number }[];
    gaps: { dimension: string; raw_score: number; weight: number }[];
    explanation: string | null; computed_at: string | null;
  }
  export interface SkillGap {
    id: string; scope: "job" | "aggregate"; job_match_id: string | null;
    skill_slug: string; skill_label: string;
    severity: "critical" | "important" | "nice_to_have";
    frequency: number; rationale: string | null; status: SkillGapStatus;
  }
  ```
  `JobCard` gains `match_score: number | null; match_band: MatchBand | null; match_status: MatchStatus | null;` (and `JobDetail` inherits). `JobQuery` gains `has_match?: boolean`.
- `endpoints.ts` — two new groups on `makeApi`'s return:
  ```ts
  matches: {
    async create(job_id: string) {
      return f<{ id: string; status: MatchStatus }>("/api/v1/matches", json("POST", { job_id }));
    },
    async get(id: string) { return f<JobMatch>(`/api/v1/matches/${id}`); },
    async list(query: { job_id?: string; min_score?: number; sort?: string } = {}) {
      const qs = new URLSearchParams(
        Object.entries(query).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
      ).toString();
      return f<{ items: JobMatch[] }>(`/api/v1/matches${qs ? `?${qs}` : ""}`);
    },
    async components(id: string) { return f<MatchComponent[]>(`/api/v1/matches/${id}/components`); },
    async recompute(body: { scope: "all" | string }) {
      return f<{ status: string; count: number }>("/api/v1/matches/recompute", json("POST", body));
    },
  },
  skillGaps: {
    async list(job_match_id: string) {
      return f<SkillGap[]>(`/api/v1/skill-gaps?scope=job&job_match_id=${job_match_id}`);
    },
    async patch(id: string, status: SkillGapStatus) {
      return f<SkillGap>(`/api/v1/skill-gaps/${id}`, { method: "PATCH",
        body: JSON.stringify({ status }), headers: { "Content-Type": "application/json" } });
    },
  },
  ```
- `query.ts` — `qk` gains `match: (jobId: string) => ["match", jobId] as const`, `matchList: (q: Record<string, unknown>) => ["match", "list", q] as const`, `skillGaps: (jobMatchId: string) => ["skill-gaps", jobMatchId] as const`.

- [ ] **Step 1: Extend `frontend/tests/api/endpoints.test.ts`** — a `describe("matches", ...)`: `create` POSTs `{job_id}` to `/api/v1/matches`; `get` GETs `/api/v1/matches/m1`; `recompute` POSTs `{scope:"all"}`; `components` GETs `/api/v1/matches/m1/components`; and `describe("skill gaps", ...)`: `list` GETs `/api/v1/skill-gaps?scope=job&job_match_id=jm1`; `patch` PATCHes `{status:"learning"}` to `/api/v1/skill-gaps/g1`. Follow the existing `as unknown as Fetcher` cast idiom.
- [ ] **Step 2–4:** run → fail → implement → `pnpm exec vitest run tests/api/endpoints.test.ts && pnpm exec tsc --noEmit && pnpm lint`.
- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/lib/query.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(matching): frontend api types, endpoints, query keys"
```

---

## Task 10: frontend — `MatchBadge` + `useMatch` hook

**Files:**
- Create: `frontend/hooks/useMatch.ts`
- Create: `frontend/components/jobs/MatchBadge.tsx`
- Test: `frontend/tests/jobs/match-badge.test.tsx`

**Interfaces:**
- Consumes: `api.matches` (Task 9), `qk.match` (Task 9), `JobMatch`/`MatchBand`/`MatchStatus` (Task 9); `useAuth`, `useMutation`, `useQuery`, `useQueryClient`; `Button`.
- Produces:
  - `useMatch.ts` — `export function useMatch(jobId: string | null, opts: { enabled?: boolean } = {})`. `const { api } = useAuth();` `useQuery({ queryKey: qk.match(jobId ?? ""), queryFn: () => api.matches.get(jobId!), enabled: (opts.enabled ?? true) && !!jobId, refetchInterval: (q) => (q.state.data?.status === "scoring" ? 2000 : false) })`. But: the match must be *requested* first (`POST /matches`). So `useMatch` also exposes a `request` mutation: `const requestMut = useMutation({ mutationFn: () => api.matches.create(jobId!), onSuccess: (r) => queryClient.setQueryData(qk.match(jobId ?? ""), (prev) => prev ?? { id: r.id, job_id: jobId, status: r.status, score: null, band: null, dimension_scores: {}, strengths: [], gaps: [], explanation: null, computed_at: null }) })`. Return `{ match: query.data ?? null, isLoading: query.isPending, request: () => requestMut.mutate(), requesting: requestMut.isPending }`. **Wrinkle:** `GET /matches/{id}` needs an id, but the FE only has `job_id`. Resolution: the query calls `api.matches.create(jobId)` (idempotent — `get_or_create` on the backend returns the existing/new row) and then reads it back — so `useMatch`'s `queryFn` is actually `async () => { const ref = await api.matches.create(jobId!); return api.matches.get(ref.id); }`. `create` is safe to call repeatedly (backend dedups). Drop the separate `request` mutation; a manual "Score" button just invalidates `qk.match(jobId)` to kick the query.
  - Final `useMatch` contract: `{ match: JobMatch | null; isLoading: boolean; refetch: () => void }` where the internal `queryFn` is the `create`→`get` pair and `refetchInterval` polls at 2 s while `status==="scoring"`.
  - `MatchBadge.tsx` — `export function MatchBadge({ score, band, status, onScore }: { score: number | null; band: MatchBand | null; status: MatchStatus | null; onScore?: () => void })`. Renders:
    - `status === "ready"` && `score != null` → a pill `"{Math.round(score)}"` with band-colored classes (`strong` → `text-positive` bg tint, `good` → `text-text`, `partial` → `text-warning`, `weak` → `text-text-muted`); tokens only.
    - `status === "scoring"` → `"Scoring…"` muted with a `<Spinner size="sm" />`.
    - `status === "failed"` → a muted `"Score unavailable"` + (if `onScore`) a tiny "Retry" button.
    - `status == null` → an `onScore` "Score" `Button variant="outline" size="sm"` (or nothing if `onScore` undefined).

- [ ] **Step 1: Write `frontend/tests/jobs/match-badge.test.tsx`** — plain `render` (no providers): `<MatchBadge score={92} band="strong" status="ready" />` → shows "92"; `status="scoring"` → shows /scoring/i; `status={null}` with an `onScore` spy → a "Score" button that calls the spy on click.
- [ ] **Step 2–4:** run → fail → implement both files → `pnpm exec vitest run tests/jobs/ && pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint`.
- [ ] **Step 5: Commit**

```bash
git add frontend/hooks/useMatch.ts frontend/components/jobs/MatchBadge.tsx frontend/tests/jobs/match-badge.test.tsx
git commit -m "feat(matching): MatchBadge + useMatch polling hook"
```

---

## Task 11: frontend — `WhyThisMatch` + `SkillGaps`

**Files:**
- Create: `frontend/components/jobs/SkillGaps.tsx`
- Create: `frontend/components/jobs/WhyThisMatch.tsx`
- Test: `frontend/tests/jobs/why-this-match.test.tsx`

**Interfaces:**
- Consumes: `useMatch` (Task 10); `api.skillGaps` (Task 9); `qk.skillGaps` (Task 9); `MatchBadge` (Task 10); `JobMatch`/`SkillGap`/`MatchComponent` (Task 9); `useAuth`, `useQuery`, `useMutation`, `useQueryClient`; `Button`, `Card`, `CardBody`, `Spinner`; `useToast`.
- Produces:
  - `SkillGaps.tsx` — `export function SkillGaps({ jobMatchId }: { jobMatchId: string })`. `useQuery({ queryKey: qk.skillGaps(jobMatchId), queryFn: () => api.skillGaps.list(jobMatchId), enabled: !!jobMatchId })`. Pending → a `<Spinner>`; empty → a muted "No skill gaps — your profile covers this role."; else a list: each row = a severity chip (`critical` → `text-danger` tint, `important` → `text-warning`, `nice_to_have` → `text-text-muted`), the `skill_label`, the `rationale` (muted, italic if present), and a `<select>` bound to `status` (`open`/`learning`/`closed`) → `patchMut = useMutation({ mutationFn: ({id, status}) => api.skillGaps.patch(id, status), onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.skillGaps(jobMatchId) }) })`.
  - `WhyThisMatch.tsx` — `export function WhyThisMatch({ jobId }: { jobId: string })`. `const { match, isLoading, refetch } = useMatch(jobId);`. States:
    - `isLoading` → `<Card><CardBody><Spinner /></CardBody></Card>`.
    - `match == null || match.status == null` → a `<Card>` "See how you match" + a "Score this job" `Button` → `refetch()`.
    - `match.status === "scoring"` → `<Card>` "Scoring this role against your profile…" + `<Spinner>` (the hook is already polling).
    - `match.status === "failed"` → `<Card>` "We couldn't score this job." + a "Try again" `Button` → `refetch()`.
    - `match.status === "ready"` → the panel:
      - Header row: `<MatchBadge score band status />` + the band word + `"vs. your current profile"` muted.
      - **Per-dimension breakdown**: for each of the 10 `dimension_scores` entries (order: sort by contribution desc using `match.strengths`/`match.gaps` is incomplete — instead fetch `api.matches.components(match.id)` via a second `useQuery(qk.match(jobId).concat("components"))` and render those; each row = ✓ (`raw_score >= 0.6`) or △, the dimension label (title-cased), and a thin contribution bar (`width: raw_score*100%`, band-neutral `bg-surface-sunk` track). Tokens only.
      - **Strengths**: `match.strengths` → a short "You're strong on: {dims}" line.
      - **Skill gaps**: `<SkillGaps jobMatchId={match.id} />`.
      - **AI explanation** (visually separated per spec §7 "fact / score / AI-explanation visually separated"): a bordered `bg-surface-sunk` block with a small "Mana's read" label + `match.explanation` (or "No summary generated." when null).

- [ ] **Step 1: Write `frontend/tests/jobs/why-this-match.test.tsx`** — mock `@/hooks/useMatch` (`vi.mock("@/hooks/useMatch", () => ({ useMatch: () => ({ match: <a ready JobMatch>, isLoading: false, refetch: vi.fn() }) }))`), `renderWithProviders(<WhyThisMatch jobId="j1" />, { api: { matches: { components: vi.fn(async () => [<one MatchComponent>]) }, skillGaps: { list: vi.fn(async () => [<one critical SkillGap>]) } } })`; assert the band word, a dimension label, the gap's `skill_label`, and the explanation text render. A second test: `useMatch` returns `{ match: null }` → a "Score this job" button is present.
- [ ] **Step 2–4:** run → fail → implement → `pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint` (whole suite — shared components).
- [ ] **Step 5: Commit**

```bash
git add frontend/components/jobs/SkillGaps.tsx frontend/components/jobs/WhyThisMatch.tsx frontend/tests/jobs/why-this-match.test.tsx
git commit -m "feat(matching): WhyThisMatch panel + SkillGaps list"
```

---

## Task 12: frontend — wire into Job Detail + Discovery

**Files:**
- Modify: `frontend/components/jobs/JobCard.tsx`
- Modify: `frontend/components/jobs/JobFilters.tsx`
- Modify: `frontend/app/(app)/jobs/[id]/page.tsx`
- Modify: `frontend/app/(app)/jobs/page.tsx`
- Test: `frontend/tests/jobs/job-card.test.tsx` (extend), `frontend/tests/jobs/discovery-page.test.tsx` (extend), `frontend/tests/jobs/job-detail-page.test.tsx` (extend)

**Interfaces:**
- Consumes: `MatchBadge` (Task 10), `WhyThisMatch` (Task 11), `api.matches.recompute` (Task 9), `qk.jobs` (Phase 4).
- Produces:
  - `JobCard.tsx` — at the `{/* match score: Phase 5 */}` slot render `<MatchBadge score={job.match_score} band={job.match_band} status={job.match_status} />` (no `onScore` on the card — the badge is read-only there; a `null` status renders nothing).
  - `JobFilters.tsx` — add a "Has match" `<input type="checkbox">` bound to the `has_match` URL param (`set("has_match", checked ? "true" : "")` via the existing `write`/`set` helpers; add `"has_match"` to `TRACKED`). Add `<option value="match">Best match</option>` to the sort `<select>`.
  - `jobs/[id]/page.tsx` — replace the entire `Match &amp; preparation` `<Card>...</Card>` block (the muted copy + disabled "Prepare application" button) with `<WhyThisMatch jobId={id} />`. Keep a separate small disabled "Prepare application" `<Button disabled title="Coming in a later release">` beneath it (Phase 8) with a one-line `{/* Phase 8: Prepare Application */}` comment.
  - `jobs/page.tsx` — read `has_match` from `useSearchParams()` into the `JobQuery` (`has_match: params.get("has_match") === "true" || undefined`); in the header, next to `<AddJobDialog />`, add a `<Button variant="outline" size="sm">` "Match all" → `recomputeMut = useMutation({ mutationFn: () => api.matches.recompute({ scope: "all" }), onSuccess: (r) => { toast({ title: `Scoring ${r.count} jobs — refresh in a moment.` }); void queryClient.invalidateQueries({ queryKey: qk.jobs }); }, onError: () => toast({ title: "Couldn't start matching.", variant: "danger" }) })`.

- [ ] **Step 1: Extend the three tests** — `job-card.test.tsx`: a card with `match_score: 88, match_band: "good", match_status: "ready"` renders "88". `discovery-page.test.tsx`: the `list` mock's `sampleJob` gets `match_*` fields → the badge shows; assert a "Match all" button is present. `job-detail-page.test.tsx`: `vi.mock("@/components/jobs/WhyThisMatch", () => ({ WhyThisMatch: () => <div>why-this-match</div> }))` → assert `why-this-match` renders in the ready layout and the old "lands in the next release" copy is gone.
- [ ] **Step 2–4:** run → fail → implement → `pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint` — whole suite green.
- [ ] **Step 5: Commit**

```bash
git add "frontend/app/(app)/jobs/[id]/page.tsx" "frontend/app/(app)/jobs/page.tsx" frontend/components/jobs/JobCard.tsx frontend/components/jobs/JobFilters.tsx frontend/tests/jobs/job-card.test.tsx frontend/tests/jobs/discovery-page.test.tsx frontend/tests/jobs/job-detail-page.test.tsx
git commit -m "feat(matching): match badges on cards, Why-this-match on detail, Match-all + has_match/sort"
```

---

## Task 13: verification & Phase 5 completion report

- [x] **Step 1: Full backend gate** — ruff clean · `lint-imports` 2 kept / 0 broken · `mypy app` clean (92 files) · `pytest --collect-only` 258, no errors · no-DB matching suites `tests/domain/matching/{test_weights,test_scorer,test_gaps,test_explainer}.py` 29 passed. (DB/Redis suites collect clean, run in CI — no local Postgres.)
- [x] **Step 2: Scorer determinism spot-check** — `deterministic: True sum==score: True`.
- [x] **Step 3: Full frontend gate** — `next lint` clean · `tsc --noEmit` exit 0 · `vitest run` 37 files / 107 tests pass.
- [x] **Step 4: OpenAPI sanity** — all 6 `/matches` + `/skill-gaps` paths present; `JobCardOut` carries `match_score` / `match_band` / `match_status`.
- [x] **Step 5: Completion report filled below; committed as** `docs: Phase 5 plan and completion report`.

---

## Phase 5 completion report

Executed subagent-driven (fresh implementer per task; subagent reviews for backend T1–T8, inline controller reviews for frontend T9–T13). Landed on branch `phase-5-job-matching` as 15 commits (12 feat + 3 ruling-fix), squashed to `main`.

- **What changed:**
  - **Schema** — migration `0008_matches` (`down_revision 0007_jobs`, single head, no generated columns): `job_matches` (score/band/dimension_scores/strengths/gaps/explanation/explanation_meta/inputs_hash/scorer_version/status/computed_at; partial-unique `uq_job_matches_profile` on `(user_id, job_id, scorer_version) WHERE resume_version_id IS NULL`), `match_components` (10 rows/match: dimension/raw_score/weight/contribution/detail/evidence), `skill_gaps` (scope job|aggregate, severity, status, rationale). `resume_version_id` / `addressed_by_roadmap_id` nullable, no FK (Phase 8/12).
  - **Pure domain** — `weights.py` (`SCORER_VERSION="v1"`, 10 `WEIGHTS` summing 1.0, `BANDS`, `SENIORITY_LADDER`, `band_for`); `scorer.py` (`ProfileSnapshot`/`JobSnapshot`/`Component`/`ScoreResult`, `score()` = 10 weighted `_dim_*` helpers, `inputs_hash()` sha256 of canonical json excl. `profile_embedding`); `gaps.py` (`derive_gaps` → `GapDraft[]`, severity from required-skill weight, required-wins dedupe); `explainer.py` (`MatchExplainer.explain` narrative + `GapRationaleWriter.write` batched rationales — prose only, never a number, **never raise** — return `None`/`{}` on structured-output *and* transport failure).
  - **Orchestration** — `MatchService` (`build_profile_snapshot`/`build_job_snapshot`, `get_or_create` [validates job → `NotFoundError`; `failed`→`scoring` on re-enqueue], `apply_score` [worker callback, flush-not-commit], `mark_failed`, `get`/`list_for_user`/`components`/`recompute`/`job_scores_for`, `list_skill_gaps`/`set_gap_status`).
  - **Worker** — `score_match` ARQ task (verbatim `_session_for` seam; idempotency skip via `inputs_hash`; F3 retry discipline; 2 non-fatal LLM calls; owns the single `session.commit()`). Registered in `WorkerSettings.functions`.
  - **REST** — `/matches` (POST 202 create, GET list, GET `/{id}`, GET `/{id}/components`, POST `/recompute` 202) + `/skill-gaps` (GET list, PATCH `/{id}`); `RecomputeIn.scope` = canonical-UUID-or-`"all"` pattern; `_bucket` "llm" tier for both POSTs (test-locked).
  - **Discovery** — `JobCardOut` +`match_score`/`match_band`/`match_status`; `?has_match=true` (EXISTS, page+count); `?sort=match` (LEFT JOIN page-query-only, `score DESC NULLS LAST`); one batched `job_scores_for` per list/detail request.
  - **Frontend** — `lib/api` types + `api.matches`/`api.skillGaps` groups + `qk.match`/`matchList`/`skillGaps`; `useMatch` (create→get queryFn, 2s poll while `scoring`); `MatchBadge` (4 states); `WhyThisMatch` (5 states, per-dimension ✓/△ + contribution bars from `/components`, strengths line, `SkillGaps` list with status `<select>`, bordered "Mana's read" block); `JobCard` badge slot; `JobFilters` "Has match" + "Best match" sort; Job Detail `<WhyThisMatch>` replaces the placeholder; Discovery "Match all" recompute button.
- **Why:** an explainable score is what turns the job corpus into a ranked shortlist and feeds Phase 12's aggregate gaps + roadmap.
- **Files changed / new deps:** 50 files (32 backend + 18 frontend), +3519/−33. **No new deps** — pgvector, `LLMProvider`, `EmbeddingsProvider`, ARQ all already present.
- **How to test:** `cd backend && uv run pytest tests/domain/matching tests/models/test_match_model.py tests/worker/test_matching_task.py tests/api/test_matches.py tests/api/test_skill_gaps.py -q` · `cd frontend && pnpm exec vitest run`
- **Regression check:** Phases 0–4 suites green; migration chain `0001 → … → 0008` linear (single alembic head `0008_matches`); `/auth`, `/resumes`, `/profile`, `/jobs` routes unchanged bar `JobCardOut` gaining 3 nullable match fields + `?has_match`/`?sort=match` on `GET /jobs`; `import-linter` `Contracts: 2 kept, 0 broken`; frontend `tsc --noEmit` + `next lint` clean; existing FE `job-card` / `discovery-page` / `job-detail-page` tests kept compiling via optional `JobCard.match_*` fields (Ruling R5).
- **Baseline:** backend `pytest --collect-only` 211 → **258** (+47); frontend **35 files / 99 tests → 37 files / 107 tests**. Local gates: `ruff` clean · `lint-imports` 2/0 · `mypy` 92 files clean · no-DB matching suites 29 passed (`test_weights`/`test_scorer`/`test_gaps`/`test_explainer`); scorer determinism `deterministic: True sum==score: True`. DB+Redis suites (Tasks 1/4/5/6/7/8 — `test_match_model`, `test_service`, `test_matching_task`, `test_matches`, `test_skill_gaps`, the new `test_jobs` case) collect clean, execute in CI only (no local Postgres).
- **Rulings made:** R1 (top-level `select` in test files), R2 (drop dead `GapDraft` line), R3 (verbatim `_session_for` seam), R4 (`get_or_create` validates the job first → `NotFoundError`), R5 (FE `JobCard.match_*` optional so Phase-4 literals compile), R6 (rate-limit bucket test not exhaustive → no update forced), R7 (`scorer` skill-test tolerance `1e-3` matches spec rounding), R8 (`scorer.py` may import sibling `weights.py`), R9 (`pytest --import-mode=importlib`, carried from Phase 4), R10 (`_normalize_enums` in worker, carried from Phase 4), R11 (`get_or_create` flips a stale `failed`→`scoring` on re-enqueue — commit `e9d7dfe`), R12 (worker builds snapshots+`inputs_hash` once, skip-check inside `try`), R13 (`explainer` catches transport exceptions, not just structured-output failure — commit `91b8d76`), R14 (`RecomputeIn.scope` tightened to a real UUID → 422 not 500; `/matches` bucket asserts added — commit `4fd8e74`), R15 (built the `JobFilters` sort `<select>` from scratch — none existed — and added `"sort"` to `TRACKED`).
- **Deviations from spec:** `semantic` dimension = direct cosine of profile-summary embedding vs mean job-chunk embedding (the RAG retriever is Phase 6); on-demand compute + FE polling every 2s (no SSE, no fan-out); `resume_version_id` nullable, no FK (Phase 8); `skill_gaps` `scope="job"` only (`scope="aggregate"` + `POST /skill-gaps/aggregate` = Phase 12); opening a Job Detail page auto-requests a match (`useMatch` `enabled` default true) — intended "match % until cached" UX, idempotent + `inputs_hash`-guarded.
- **Not verified here:** real embedding-provider semantic quality (fake provider only exercises the cosine mechanics); LLM narrative/rationale quality (fake provider stubs prose to empty); `scope="aggregate"` gaps + roadmap (Phase 12); re-score on profile edit (Phase 12); the `understand_job` agent flow (Phase 7); tailored-résumé matching (Phase 8); the DB+Redis suites run first in CI.

---

## Self-Review

**1. Spec coverage (Phase 5 of §9 + §2.2 `/matches`/`/skill-gaps` + §4 `matching/` + §5 tables + D7):**
- deterministic `scorer` (10 dims + weights) → Task 2. ✓ (pure module, weights sum-to-1 test, D7.)
- `match_components` + evidence → Tasks 1 (table) + 2 (`Component.evidence`) + 4 (`apply_score` writes them). ✓
- `MatchExplainer` (narrates only) → Task 3 (`explain` returns prose, never a number; non-fatal). ✓
- `skill_gaps` (job scope) → Tasks 1 (table) + 3 (`derive_gaps`) + 4 (`apply_score` writes) + 7 (`/skill-gaps` API). ✓ (aggregate scope deferred to Phase 12, flagged.)
- "Why this match?" UI + ✓/△ + narrative + bands → Tasks 10–12. ✓
- `POST /matches` `{resume_version_id?, job_id}` → Task 6 (`resume_version_id` omitted — nullable, Phase 8). ✓
- `GET /matches?job_id=&min_score=&sort=` · `GET /{id}` · `GET /{id}/components` · `POST /recompute {scope}` → Task 6. ✓
- `GET /skill-gaps?scope=job|aggregate&job_match_id=` · `PATCH /{id} {status}` → Task 7. ✓ (`POST /aggregate` deferred to Phase 12.)
- `job_matches` columns (§5) → Task 1 (score/band/dimension_scores/strengths/gaps/explanation/explanation_meta/inputs_hash/scorer_version/computed_at, unique on version). ✓
- match % on job cards + "Scoring…" until cached (§7 J2) → Tasks 8 + 10 + 12. ✓
- "fact / score / AI-explanation visually separated" (§7 J2) → Task 11 (`WhyThisMatch` — JD facts already on the page, score in `MatchBadge`, explanation in a bordered "Mana's read" block). ✓

**2. Placeholder scan:** Tasks 1–3 carry literal code + tests; Tasks 4–13 carry full Produces contracts + concrete test bodies and describe the implementations against them (accepted style, Phases 2b–4). The dimension formulas in Task 2 are fully specified (every branch, every `detail` key). One seam is named: `score_match`'s `_session_for` verbatim copy (Ruling-style, as Phases 2a/3/4). No "TBD".

**3. Type consistency:**
- `ProfileSnapshot` / `JobSnapshot` / `Component` / `ScoreResult` (Task 2) — consumed by Tasks 3 (`derive_gaps` takes `Component`), 4 (`score`, `apply_score`), 5 (worker). Field names identical across.
- `GapDraft` (Task 3) — `{skill_id, slug, label, severity}` — consumed by Task 4 (`apply_score` gaps param) + Task 5.
- `SCORER_VERSION` (Task 2) — used by Task 4 (`get_or_create`, `job_scores_for`) + Task 8 (`_filtered`, list join).
- `MatchService.job_scores_for -> dict[uuid, tuple[float|None, str|None, str]]` (Task 4) — consumed by Task 8's `_card`.
- `JobCardOut` +3 fields (Task 8) — mirrored by the FE `JobCard` type (Task 9), rendered by `MatchBadge` (Task 10) inside `JobCard.tsx` (Task 12).
- `JobMatch` FE type (Task 9) — `{id, job_id, status, score, band, dimension_scores, strengths, gaps, explanation, computed_at}` mirrors `MatchOut` (Task 6). Consumed by `useMatch` (10), `WhyThisMatch` (11).
- Migration chain `0007_jobs` → `0008_matches` (Task 1). ✓
- Rate-limit `_bucket` "llm" tier for `POST /matches` + `/recompute` (Task 6) — consistent with §6.5.

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-09-02-phase-5-job-matching.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between, whole-branch review at the end.

**2. Inline Execution** — `superpowers:executing-plans`, batched with checkpoints.

**Environment:** `uv` at `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`; backend `ruff`/`mypy`/`lint-imports` + the no-DB matching suites run locally; DB+Redis-backed tests (Tasks 1, 4, 5, 6, 7, 8) verify in CI. Frontend runs fully locally with `pnpm exec vitest run`. The `semantic` cosine and both LLM prose calls are exercised with the fake providers (deterministic); real quality lands with real providers in Phase 6+.
