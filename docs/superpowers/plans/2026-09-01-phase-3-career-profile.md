# Phase 3 — Career Profile Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a résumé is confirmed, a background pass maps the free-text skills scattered across the profile's experiences and projects onto a controlled taxonomy, records where each skill was found, and recomputes a per-dimension strength breakdown — all surfaced on the `/profile` page.

**Architecture:** A new `skills/` domain package owns the controlled taxonomy (`skills` shared table, ~200 hand-curated AI/ML/software entries seeded from a JSON file, embedded at seed time) and a `SkillNormalizer` (exact slug/alias match, then embedding near-match). A new `ProfileBuilder` (`profile/builder.py`) reads every `tech[]` on the user's experiences/projects plus the primary résumé's extracted skills, normalizes each, and upserts `profile_skills` rows carrying `evidence_refs` back to the source sub-entities. It runs as an ARQ task `build_profile(user_id)` enqueued at the end of `ResumeService.confirm_profile` and by a manual `POST /profile/rebuild`. The existing deterministic strength scorer gains a per-dimension breakdown and a "skills mapped" dimension.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, ARQ + Redis, pgvector (`Vector` column), the existing `EmbeddingsProvider` abstraction (`fake` in CI). Frontend: Next.js 15 / React 19 / TS strict / @tanstack/react-query / Vitest. `uv` at `C:\Users\chitt\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`.

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` — Phase 3 of §9, §2.2 (`skills/` + `profile/` packages), §4.3 (`profile_builder` node), §5.2/§5.3 (`skills`, `profile_skills` tables), §5.4 (skills vector search), §3.2 J1 ("corrections … profile populated"). Phases 0–2b are complete on `main`.

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtimes:** Python 3.12; PostgreSQL 16 + `pgvector`; Redis 7. Migration chain: `0005_resumes` is head → this phase adds `0006_skills`.
- **PKs / timestamps / enums / soft-delete / user isolation / audit:** exactly as Phases 1–2 — `uuid` `gen_random_uuid()`; `timestamptz` + `set_updated_at` trigger; `text` + named `CHECK`; `user_id NOT NULL` on user-scoped tables; the `skills` table is **shared/seeded** (no `user_id`, no owner column); `import-linter` layers `api > worker > domain > infra > core > models`, `domain/*` never imports `api`/`worker`.
- **Embeddings:** all vector work goes through `get_embeddings_provider(settings)` (`app.domain.embeddings.factory`). CI and tests run `EMBEDDINGS_PROVIDER=fake`; `EMBED_DIM=1024`. `FakeEmbeddingsProvider` returns a deterministic **random** unit vector per exact input string — identical strings match at cosine 1.0, unrelated strings are ~orthogonal. Tests that exercise the embedding path must embed the *same* string they later query.
- **Skill taxonomy:** `app/domain/skills/taxonomy.json` — hand-curated, ~180–220 entries, each `{slug, label, category, aliases}`. `slug` is `[a-z0-9+#.-]+`, globally unique. `category` ∈ `{language, ml_framework, ml_technique, data, cloud, devops, backend, frontend, database, tooling, practice}`. `python -m app.seed skills` upserts by slug and (re)computes `embedding`. Migration `0006` creates the tables **empty**; seeding is a separate step.
- **`profile_builder` scope (v1):** deterministic only — exact + embedding match, no LLM. The "light LLM normalize" (company-name canonicalization, seniority/proficiency/years inference) is **deferred**. `proficiency` and `years` on `profile_skills` stay `NULL` in this phase. Résumé-chunk-level evidence is Phase 6; `evidence_refs` here point only at `profile_experiences` / `profile_projects` / `resumes` ids.
- **`build_profile` task:** own `AsyncSessionLocal` via a `_session_for()` seam (mirrors `app/worker/tasks/resume.py`); dead-letters on failure and re-raises; no SSE (fast, silent). Idempotent — re-running replaces the `source="resume_extraction"` skill set and never touches `source="user"` rows.
- **Deferred, flagged:** Résumé Workspace 3-pane shell → Phase 8; manual `profile_skills` add/edit/remove → later; the `/resume` route naming collision with Phase 2b's upload flow → Phase 8.
- **Workflow:** TDD, DRY, YAGNI, commit per green step. Backend commands from `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run mypy app`, `uv run lint-imports`. Frontend from `frontend/`: `pnpm exec vitest run`, `pnpm exec tsc --noEmit`, `pnpm lint` (`pnpm test` hangs in watch mode). DB-backed tests need Postgres+Redis — CI provides them.

---

## File Structure

**Created — backend**
- `backend/app/models/skill.py` — `Skill`, `ProfileSkill` ORM models.
- `backend/alembic/versions/0006_skills.py` — the two tables + indexes.
- `backend/app/domain/skills/__init__.py` (empty), `backend/app/domain/skills/taxonomy.json`, `backend/app/domain/skills/normalizer.py` — `SkillNormalizer`, `SkillMatch`.
- `backend/app/domain/profile/builder.py` — `ProfileBuilder`, `BuildResult`.
- `backend/app/seed.py` — `python -m app.seed skills` CLI.
- `backend/app/worker/tasks/profile.py` — `build_profile` ARQ task.
- Tests under `backend/tests/` alongside each unit.

**Modified — backend**
- `backend/app/models/__init__.py` — import `skill`.
- `backend/app/domain/profile/strength.py` — per-dimension breakdown + `skills_mapped` dimension.
- `backend/app/domain/profile/service.py` — `_recompute` passes a skill count; new `list_skills`.
- `backend/app/domain/resume/service.py` — `confirm_profile` enqueues `build_profile`.
- `backend/app/worker/tasks/__init__.py` + `backend/app/worker/main.py` — register `build_profile`.
- `backend/app/api/v1/profile.py` + `backend/app/api/v1/schemas/profile.py` — `GET /profile/skills`, `POST /profile/rebuild`, `dimensions` on `StrengthOut`.

**Modified — frontend**
- `frontend/lib/api/types.ts` — `Strength.dimensions`, new `ProfileSkill`.
- `frontend/lib/api/endpoints.ts` — `api.profile.skills()`, `api.profile.rebuild()`.
- `frontend/lib/query.ts` — `qk.skills`.
- `frontend/components/common/StrengthMeter.tsx` — optional per-dimension breakdown.
- `frontend/components/profile/ProfileSkills.tsx` (new) + `frontend/app/(app)/profile/page.tsx` — the Skills card.

---

## Task 1: `skills` + `profile_skills` models + migration `0006`

**Files:**
- Create: `backend/app/models/skill.py`, `backend/alembic/versions/0006_skills.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/test_skill_model.py`

**Interfaces — Produces:**
- `app.models.skill.Skill` (`Base`, `TimestampMixin`): `id` uuid pk · `slug` `String(120)` unique not null · `label` `String(160)` not null · `category` `String(60)` not null · `aliases` `ARRAY(Text)` not null server_default `'{}'` · `embedding` `Vector(1024)` nullable · ts. Index: `Index("ix_skills_aliases", "aliases", postgresql_using="gin")`.
- `app.models.skill.ProfileSkill` (`Base`, `TimestampMixin`): `id` uuid pk · `user_id` uuid FK `users.id` CASCADE not null · `profile_id` uuid FK `career_profiles.id` CASCADE not null · `skill_id` uuid FK `skills.id` CASCADE not null · `proficiency` `String(16)` nullable · `years` `Numeric(4,1)` nullable · `source` `String(20)` not null server_default `'resume_extraction'` · `evidence_refs` `JSONB` not null server_default `'[]'::jsonb` (`Mapped[list[dict[str, Any]]]`) · ts. `UniqueConstraint("profile_id", "skill_id", name="uq_profile_skills_profile_skill")`; `CheckConstraint("proficiency in ('beginner','intermediate','advanced','expert')", name="profile_skills_proficiency_valid")`; `CheckConstraint("source in ('user','resume_extraction','inferred')", name="profile_skills_source_valid")`; `Index("ix_profile_skills_profile", "profile_id")`.
- Migration `0006_skills` (`down_revision = "0005_resumes"`): both tables, both `updated_at` triggers, the GIN index, HNSW index `ix_skills_embedding` (`postgresql_using="hnsw"`, `postgresql_with={"m": 16, "ef_construction": 64}`, `postgresql_ops={"embedding": "vector_cosine_ops"}`), the unique + check constraints.

- [ ] **Step 1: Write the failing test**

`backend/tests/models/test_skill_model.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.skill import ProfileSkill, Skill
from app.models.user import User
from app.models.profile import CareerProfile


async def _profile(db_session, email="sk@example.com"):
    u = User(email=email, password_hash="x", full_name="S")
    db_session.add(u)
    await db_session.flush()
    p = CareerProfile(user_id=u.id)
    db_session.add(p)
    await db_session.flush()
    return u, p


async def test_skill_slug_unique(db_session):
    db_session.add(Skill(slug="pytorch", label="PyTorch", category="ml_framework"))
    await db_session.flush()
    db_session.add(Skill(slug="pytorch", label="PyTorch 2", category="ml_framework"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_profile_skill_defaults_and_unique(db_session):
    u, p = await _profile(db_session)
    s = Skill(slug="fastapi", label="FastAPI", category="backend")
    db_session.add(s)
    await db_session.flush()
    ps = ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id)
    db_session.add(ps)
    await db_session.flush()
    got = (await db_session.execute(select(ProfileSkill).where(ProfileSkill.id == ps.id))).scalar_one()
    assert got.source == "resume_extraction"
    assert got.evidence_refs == []
    assert got.proficiency is None
    db_session.add(ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_profile_skill_source_check(db_session):
    u, p = await _profile(db_session, "sk2@example.com")
    s = Skill(slug="numpy", label="NumPy", category="data")
    db_session.add(s)
    await db_session.flush()
    ps = ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id)
    ps.source = "bogus"
    db_session.add(ps)
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 2: Run — expect fail** (`ModuleNotFoundError: app.models.skill`).

- [ ] **Step 3: Implement.** Model style mirrors `backend/app/models/resume.py` (SQLAlchemy 2.0 `Mapped` / `mapped_column`, `Base` + `TimestampMixin`, `import uuid`, `Mapped[uuid.UUID]` on `id`/FKs, `from typing import Any` for the JSONB). `from pgvector.sqlalchemy import Vector`. Migration mirrors `backend/alembic/versions/0005_resumes.py` (hand-written, `_TS`, `sa.text("gen_random_uuid()")`, trigger `op.execute("CREATE TRIGGER trg_<t>_set_updated_at …")`, `downgrade()` drops triggers then tables). Add `from app.models import skill as skill` to `models/__init__.py` between `resume` and `user`.

- [ ] **Step 4: Run — expect pass.** DB-backed: verify in CI. Locally: `cd backend && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run python -c "from app.models.skill import Skill, ProfileSkill; import app.models; print(Skill.__tablename__, ProfileSkill.__tablename__)" && "$UV" run python -m py_compile alembic/versions/0006_skills.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/skill.py backend/app/models/__init__.py backend/alembic/versions/0006_skills.py backend/tests/models/test_skill_model.py
git commit -m "feat(models): skills taxonomy + profile_skills tables (migration 0006)"
```

---

## Task 2: skill taxonomy JSON + `app.seed` CLI

**Files:**
- Create: `backend/app/domain/skills/__init__.py` (empty), `backend/app/domain/skills/taxonomy.json`, `backend/app/seed.py`
- Test: `backend/tests/domain/skills/test_taxonomy.py`

**Interfaces — Produces:**
- `app/domain/skills/taxonomy.json` — a JSON array of `{"slug": str, "label": str, "category": str, "aliases": [str, …]}`. **180–220 entries** spanning every `category` in the Global Constraints list, weighted toward AI/ML/software (Python, PyTorch, TensorFlow, JAX, scikit-learn, Hugging Face Transformers, LangChain, pandas, NumPy, FastAPI, Django, React, Next.js, PostgreSQL, pgvector, Redis, Docker, Kubernetes, AWS, GCP, Terraform, Git, MLflow, Weights & Biases, RAG, fine-tuning, prompt engineering, vector databases, …). `aliases` are lowercase surface forms real résumés use (`"torch"` for pytorch, `"sklearn"` for scikit-learn, `"k8s"` for kubernetes, `"gha"` for github-actions, `"pg"` for postgresql).
- `app.seed`:
  - `async def load_taxonomy() -> list[dict[str, Any]]` — reads and returns `taxonomy.json` (path relative to this module).
  - `async def seed_skills() -> int` — opens `AsyncSessionLocal`, for each entry upserts `Skill` by `slug` (insert or update `label`/`category`/`aliases`), computes `embedding` via `get_embeddings_provider(get_settings()).embed_query(f"{label}: {', '.join(aliases)}" if aliases else label)`, commits, returns the count.
  - `if __name__ == "__main__":` — `python -m app.seed skills` → `asyncio.run(seed_skills())` and print `f"seeded {n} skills"`; any other arg → exit 2 with a usage line.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/skills/test_taxonomy.py` (no DB):

```python
import re

from app.seed import load_taxonomy

_CATEGORIES = {
    "language", "ml_framework", "ml_technique", "data", "cloud", "devops",
    "backend", "frontend", "database", "tooling", "practice",
}
_SLUG = re.compile(r"^[a-z0-9+#.-]+$")


async def test_taxonomy_is_well_formed():
    entries = await load_taxonomy()
    assert 150 <= len(entries) <= 260
    slugs = [e["slug"] for e in entries]
    assert len(slugs) == len(set(slugs)), "slugs must be unique"
    for e in entries:
        assert set(e) >= {"slug", "label", "category", "aliases"}
        assert _SLUG.match(e["slug"]), e["slug"]
        assert e["category"] in _CATEGORIES, e
        assert isinstance(e["aliases"], list)
        assert e["label"].strip()


async def test_core_ml_skills_present():
    slugs = {e["slug"] for e in await load_taxonomy()}
    for expected in {"python", "pytorch", "tensorflow", "scikit-learn", "fastapi",
                     "docker", "kubernetes", "postgresql", "react", "langchain"}:
        assert expected in slugs, expected
```

- [ ] **Step 2: Run — expect fail** (`ModuleNotFoundError: app.seed`).

- [ ] **Step 3: Implement** `taxonomy.json` (fill to ~200 entries) and `app/seed.py`. `load_taxonomy` uses `json.loads((Path(__file__).parent / "domain" / "skills" / "taxonomy.json").read_text("utf-8"))` — wait, `seed.py` is at `app/seed.py`, so the path is `Path(__file__).parent / "domain" / "skills" / "taxonomy.json"`. `seed_skills` uses `insert(Skill).values(...).on_conflict_do_update(index_elements=["slug"], set_={...})` (`from sqlalchemy.dialects.postgresql import insert`).

- [ ] **Step 4: Run — expect pass** (`cd backend && "$UV" run pytest tests/domain/skills/test_taxonomy.py -q && "$UV" run ruff check . && "$UV" run mypy app`). `seed_skills` itself is DB-backed → smoke it in Task 11 / CI.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/skills/__init__.py backend/app/domain/skills/taxonomy.json backend/app/seed.py backend/tests/domain/skills/test_taxonomy.py
git commit -m "feat(skills): curated skill taxonomy + app.seed skills CLI"
```

---

## Task 3: `SkillNormalizer`

**Files:**
- Create: `backend/app/domain/skills/normalizer.py`
- Test: `backend/tests/domain/skills/test_normalizer.py`

**Interfaces:**
- Consumes: `EmbeddingsProvider`; `app.models.skill.Skill`.
- Produces:
  - `@dataclass(frozen=True) SkillMatch`: `skill_id: uuid.UUID`, `slug: str`, `label: str`, `method: Literal["exact", "embedding"]`, `score: float`.
  - `class SkillNormalizer(session: AsyncSession, embeddings: EmbeddingsProvider, *, threshold: float = 0.82)`.
    - `async def load(self) -> None` — `SELECT id, slug, label, aliases FROM skills`; builds `self._exact: dict[str, tuple[uuid.UUID, str, str]]` keyed by `_norm(slug)` and `_norm(alias)` for every alias; records whether any row has a non-null embedding (`self._has_embeddings`).
    - `@staticmethod def _norm(s: str) -> str` — `s.strip().lower()`, collapse internal whitespace to single spaces, strip leading/trailing chars not in `[a-z0-9+#.]`. Keeps `+ # .` (c++, c#, node.js).
    - `async def normalize(self, raw: str) -> SkillMatch | None` — `_norm(raw)` in `self._exact` → `SkillMatch(method="exact", score=1.0)`. Else if `self._has_embeddings`: `q = await self.embeddings.embed_query(raw)`; `SELECT id, slug, label, 1 - (embedding <=> :q) AS sim FROM skills WHERE embedding IS NOT NULL ORDER BY embedding <=> :q LIMIT 1` (bind `:q` as a pgvector param — use `sqlalchemy.text` with a `::vector` cast on a JSON-list string, or `pgvector.sqlalchemy`'s type); `sim >= threshold` → `SkillMatch(method="embedding", score=float(sim))`, else `None`. Else `None`.
    - `async def normalize_many(self, raws: Iterable[str]) -> dict[str, SkillMatch]` — de-dupes case-insensitively, calls `normalize` once per distinct raw, returns `{original_raw: match}` for hits only.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/skills/test_normalizer.py` (DB-backed):

```python
import pytest

from app.core.config import get_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.skills.normalizer import SkillNormalizer
from app.models.skill import Skill


@pytest.fixture
def embeddings():
    return get_embeddings_provider(get_settings())


async def _seed(db_session, embeddings, rows):
    for slug, label, cat, aliases, embed_text in rows:
        s = Skill(slug=slug, label=label, category=cat, aliases=aliases)
        if embed_text is not None:
            s.embedding = await embeddings.embed_query(embed_text)
        db_session.add(s)
    await db_session.flush()


async def test_exact_and_alias_match(db_session, embeddings):
    await _seed(db_session, embeddings, [
        ("pytorch", "PyTorch", "ml_framework", ["torch"], None),
        ("scikit-learn", "scikit-learn", "ml_framework", ["sklearn"], None),
    ])
    n = SkillNormalizer(db_session, embeddings)
    await n.load()
    m1 = await n.normalize("  PyTorch ")
    assert m1 and m1.slug == "pytorch" and m1.method == "exact"
    m2 = await n.normalize("sklearn")
    assert m2 and m2.slug == "scikit-learn" and m2.method == "exact"
    assert await n.normalize("xyzzy-nope") is None


async def test_embedding_near_match(db_session, embeddings):
    # FakeEmbeddingsProvider is deterministic per exact string: seed the row's
    # embedding from a phrase, then query that same phrase → cosine 1.0.
    await _seed(db_session, embeddings, [
        ("rag", "Retrieval-Augmented Generation", "ml_technique", [],
         "retrieval augmented generation pipeline over documents"),
    ])
    n = SkillNormalizer(db_session, embeddings, threshold=0.9)
    await n.load()
    m = await n.normalize("retrieval augmented generation pipeline over documents")
    assert m and m.slug == "rag" and m.method == "embedding" and m.score >= 0.9


async def test_normalize_many_dedupes(db_session, embeddings):
    await _seed(db_session, embeddings, [
        ("python", "Python", "language", ["py"], None),
    ])
    n = SkillNormalizer(db_session, embeddings)
    await n.load()
    out = await n.normalize_many(["Python", "python", "PY", "unknown"])
    assert set(out) <= {"Python", "python", "PY"}
    assert all(v.slug == "python" for v in out.values())
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** For the pgvector query, bind the query vector as a string `"[" + ",".join(map(repr, q)) + "]"` and use `text("... ORDER BY embedding <=> cast(:q as vector) LIMIT 1").bindparams(q=q_str)`, or reuse `Skill.embedding.cosine_distance(q)` from `pgvector.sqlalchemy` if cleaner. `normalizer.py` imports only `app.models.skill`, `app.domain.embeddings.provider`, stdlib, sqlalchemy — layer-internal, no `.importlinter` change.

- [ ] **Step 4: Run — expect pass** (DB → CI). Local: `ruff` + `mypy` + `lint-imports`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/skills/normalizer.py backend/tests/domain/skills/test_normalizer.py
git commit -m "feat(skills): SkillNormalizer — exact/alias + embedding near-match"
```

---

## Task 4: `ProfileBuilder`

**Files:**
- Create: `backend/app/domain/profile/builder.py`
- Test: `backend/tests/domain/profile/test_builder.py`

**Interfaces:**
- Consumes: `SkillNormalizer` (Task 3); `ProfileService` (`get_or_create`, `_recompute`); `Skill`/`ProfileSkill` (Task 1); `ProfileExperience`/`ProfileProject` (`app.models.profile`); `Resume` (`app.models.resume`); `get_embeddings_provider`, `get_settings`.
- Produces:
  - `@dataclass(frozen=True) BuildResult`: `matched: int`, `evidence_total: int`, `unmatched: list[str]`.
  - `class ProfileBuilder(session: AsyncSession, *, embeddings: EmbeddingsProvider | None = None)`.
    - `async def rebuild(self, user_id: uuid.UUID) -> BuildResult`:
      1. `profile = await ProfileService(self.session).get_or_create(user_id)`.
      2. Collect `(raw: str, kind: str, ref_id: uuid.UUID)` from: every non-empty string in each `ProfileExperience.tech` for this `profile_id` → `kind="experience"`, `ref_id=exp.id`; same for `ProfileProject.tech` → `kind="project"`; and, from the user's primary non-deleted `Resume` with `status="extracted"` and a non-null `extraction`, every string in `extraction.get("skills", [])` → `kind="resume"`, `ref_id=resume.id`.
      3. `norm = SkillNormalizer(self.session, self.embeddings or get_embeddings_provider(get_settings()))`; `await norm.load()`.
      4. For each distinct raw (case-insensitive): `m = await norm.normalize(raw)`. Group hits by `m.skill_id` → `evidence_refs: list[dict]` = `[{"kind": kind, "ref_id": str(ref_id), "raw": raw}]` for every `(kind, ref_id, raw)` that produced that skill (dedupe identical dicts).
      5. `DELETE FROM profile_skills WHERE profile_id = :pid AND source = 'resume_extraction'`.
      6. For each grouped `skill_id`: `self.session.add(ProfileSkill(user_id=user_id, profile_id=profile.id, skill_id=skill_id, source="resume_extraction", evidence_refs=<list>))`.
      7. `await self.session.flush()`; `await ProfileService(self.session)._recompute(profile)`.
      8. `return BuildResult(matched=<distinct skill_ids>, evidence_total=<sum of evidence list lengths>, unmatched=<sorted distinct raws with no match>)`.
- `builder.py` imports `app.models.*`, `app.domain.profile.service`, `app.domain.skills.normalizer`, `app.domain.embeddings.*` — all layer-internal.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/profile/test_builder.py` (DB-backed):

```python
from sqlalchemy import select

from app.core.config import get_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.profile.builder import ProfileBuilder
from app.domain.profile.service import ProfileService
from app.models.profile import ProfileExperience, ProfileProject
from app.models.skill import ProfileSkill, Skill
from app.domain.auth.service import AuthService


async def _seed_taxonomy(db_session):
    for slug, label, cat, aliases in [
        ("pytorch", "PyTorch", "ml_framework", ["torch"]),
        ("fastapi", "FastAPI", "backend", []),
        ("python", "Python", "language", ["py"]),
    ]:
        db_session.add(Skill(slug=slug, label=label, category=cat, aliases=aliases))
    await db_session.flush()


async def _user(db_session, email):
    reg = await AuthService(db_session).register(email, "correct-passphrase", "B",
                                                 ip=None, user_agent=None)
    return reg.user.id


async def test_rebuild_maps_tech_with_evidence(db_session):
    await _seed_taxonomy(db_session)
    uid = await _user(db_session, "b1@example.com")
    profile = await ProfileService(db_session).get_or_create(uid)
    e = ProfileExperience(user_id=uid, profile_id=profile.id, company="Acme", title="ML Eng",
                          source="resume_extraction", order_index=0, tech=["PyTorch", "Python"])
    p = ProfileProject(user_id=uid, profile_id=profile.id, name="Thing",
                       source="resume_extraction", order_index=0, tech=["torch", "xyzzy"])
    db_session.add_all([e, p])
    await db_session.flush()

    res = await ProfileBuilder(db_session).rebuild(uid)
    assert res.matched == 3  # pytorch, python, fastapi? no -> pytorch, python  (2)
    # (adjust: matched == 2; "xyzzy" unmatched)
    rows = (await db_session.execute(
        select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
    )).scalars().all()
    by_slug = {}
    for ps in rows:
        s = (await db_session.execute(select(Skill).where(Skill.id == ps.skill_id))).scalar_one()
        by_slug[s.slug] = ps
    assert set(by_slug) == {"pytorch", "python"}
    kinds = {ev["kind"] for ev in by_slug["pytorch"].evidence_refs}
    assert kinds == {"experience", "project"}
    assert "xyzzy" in res.unmatched


async def test_rebuild_is_idempotent_and_keeps_user_skills(db_session):
    await _seed_taxonomy(db_session)
    uid = await _user(db_session, "b2@example.com")
    profile = await ProfileService(db_session).get_or_create(uid)
    db_session.add(ProfileExperience(user_id=uid, profile_id=profile.id, company="A", title="T",
                                     source="resume_extraction", order_index=0, tech=["FastAPI"]))
    fa = (await db_session.execute(select(Skill).where(Skill.slug == "fastapi"))).scalar_one()
    db_session.add(ProfileSkill(user_id=uid, profile_id=profile.id, skill_id=fa.id, source="user"))
    await db_session.flush()

    await ProfileBuilder(db_session).rebuild(uid)
    await ProfileBuilder(db_session).rebuild(uid)
    rows = (await db_session.execute(
        select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
    )).scalars().all()
    # one user fastapi + one resume_extraction fastapi is a UNIQUE violation on
    # (profile_id, skill_id) — so the builder must SKIP a skill that already has a
    # source="user" row. Assert: exactly one fastapi row, still source="user".
    assert len(rows) == 1 and rows[0].source == "user"
```

> **Design note for the implementer:** the `(profile_id, skill_id)` unique constraint means step 6 must **not** insert a `resume_extraction` row for a skill that already has a `source="user"` row. After the `DELETE … WHERE source='resume_extraction'`, load the surviving `skill_id`s for the profile and skip those in the insert loop. `BuildResult.matched` counts skills newly written by this run.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** to the Produces contract + the design note. Fix the first test's `assert res.matched` to the real value (2) when writing it.

- [ ] **Step 4: Run — expect pass** (DB → CI). Local: `ruff` + `mypy` + `lint-imports`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/profile/builder.py backend/tests/domain/profile/test_builder.py
git commit -m "feat(profile): ProfileBuilder — map profile tech onto the skill taxonomy with evidence"
```

---

## Task 5: strength breakdown

**Files:**
- Modify: `backend/app/domain/profile/strength.py`, `backend/app/domain/profile/service.py`
- Test: `backend/tests/domain/profile/test_strength.py` (extend), `backend/tests/domain/profile/test_profile_service.py` (extend)

**Interfaces:**
- Consumes: `ProfileSkill` (Task 1).
- Produces:
  - `strength.py`: `_WEIGHTS` becomes `list[tuple[str, int, str, str]]` = `(key, weight, label, hint)`. Add `("skills_mapped", 8, "Skills mapped", "Upload a résumé so Mana can map your skills")`; rebalance so the weights still sum to **100** — reduce `experience` `20 → 16` and `links` `10 → 6`. Full new list, in order: `location`(8,"Location"), `links`(6,"Profile links"), `goals`(10,"Career goals"), `preferred_roles`(8,"Target roles"), `seniority`(6,"Seniority"), `years_experience`(6,"Years of experience"), `salary`(6,"Salary expectations"), `experience`(16,"Work experience"), `education`(12,"Education"), `projects`(10,"Projects"), `certifications`(4,"Certifications"), `skills_mapped`(8,"Skills mapped").
  - `@dataclass(frozen=True) StrengthDimension`: `key: str`, `label: str`, `earned: int`, `max: int`, `hint: str`, `met: bool`.
  - `StrengthResult` gains `dimensions: list[StrengthDimension]`.
  - `compute_strength(profile, counts, *, skill_count: int = 0) -> StrengthResult` — adds `checks["skills_mapped"] = skill_count >= 5`; `dimensions = [StrengthDimension(key, label, earned=(w if checks[key] else 0), max=w, hint=hint, met=checks[key]) for key, w, label, hint in _WEIGHTS]`; `score`/`completeness`/`missing` computed exactly as before over the new 12-key set.
  - `service.py`: `ProfileService._recompute` counts `ProfileSkill` for `profile.id` and passes `skill_count=` to `compute_strength`. New `async def list_skills(self, user_id) -> list[tuple[ProfileSkill, Skill]]` — `select(ProfileSkill, Skill).join(Skill).where(ProfileSkill.user_id == user_id).order_by(Skill.category, Skill.label)`.

- [ ] **Step 1: Write / update the failing tests**

Extend `backend/tests/domain/profile/test_strength.py`:

```python
def test_dimensions_sum_to_score_and_100(_a_blank_profile):
    from app.domain.profile.strength import compute_strength, ProfileCounts
    r = compute_strength(_a_blank_profile, ProfileCounts(0, 0, 0, 0), skill_count=0)
    assert sum(d.max for d in r.dimensions) == 100
    assert sum(d.earned for d in r.dimensions) == r.score
    assert {d.key for d in r.dimensions} >= {"skills_mapped", "experience", "links"}
    sm = next(d for d in r.dimensions if d.key == "skills_mapped")
    assert sm.met is False and sm.earned == 0 and sm.max == 8


def test_skills_mapped_dimension_flips_at_five(_a_blank_profile):
    from app.domain.profile.strength import compute_strength, ProfileCounts
    assert not compute_strength(_a_blank_profile, ProfileCounts(0,0,0,0), skill_count=4)\
        .dimensions[-1].met
    lit = compute_strength(_a_blank_profile, ProfileCounts(0,0,0,0), skill_count=5)
    assert next(d for d in lit.dimensions if d.key == "skills_mapped").met
```

> Use whatever blank-`CareerProfile` fixture/helper `test_strength.py` already has; add one if absent (a bare `CareerProfile()` is fine — it's not persisted).

Extend `test_profile_service.py` with a DB test: create a profile, add 5 `ProfileSkill` rows, `await ProfileService(db).get_or_create(uid)` then re-`_recompute`, assert `profile.completeness["skills_mapped"] is True` and `profile.profile_strength` rose by 8.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** The existing `compute_strength` tests that unpack `_WEIGHTS` as 3-tuples must be updated to 4-tuples.

- [ ] **Step 4: Run — expect pass** (`cd backend && "$UV" run pytest tests/domain/profile/test_strength.py -q` locally; the service test is DB → CI). `ruff` + `mypy`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/profile/strength.py backend/app/domain/profile/service.py backend/tests/domain/profile/test_strength.py backend/tests/domain/profile/test_profile_service.py
git commit -m "feat(profile): per-dimension strength breakdown + skills-mapped dimension"
```

---

## Task 6: `build_profile` ARQ task + confirm-profile hook

**Files:**
- Create: `backend/app/worker/tasks/profile.py`
- Modify: `backend/app/worker/tasks/__init__.py`, `backend/app/worker/main.py`, `backend/app/domain/resume/service.py`
- Test: `backend/tests/worker/test_profile_task.py`

**Interfaces:**
- Consumes: `ProfileBuilder` (Task 4); `AsyncSessionLocal`; `record_failure`; `enqueue` (`app.core.queue`).
- Produces:
  - `app.worker.tasks.profile.build_profile(ctx: dict[str, Any], user_id: str) -> dict[str, Any]` — `async with _session_for() as session:` (a local copy of the `_session_for` async-CM seam from `app/worker/tasks/resume.py`); `try:` `res = await ProfileBuilder(session).rebuild(uuid.UUID(user_id))`; `await session.commit()`; `return {"user_id": user_id, "matched": res.matched, "unmatched": len(res.unmatched)}`. `except Exception as exc:` `await session.rollback()`; `await record_failure("build_profile", args=(user_id,), kwargs={}, error=exc)`; `raise`.
  - `worker/tasks/__init__.py` exports `build_profile`; `worker/main.py` `WorkerSettings.functions` includes it.
  - `ResumeService.confirm_profile` — after the final `await self._audit("resume.confirm_profile", …)` call, `await enqueue("build_profile", str(user_id))`.

- [ ] **Step 1: Write the failing test**

`backend/tests/worker/test_profile_task.py` (DB-backed):

```python
from sqlalchemy import select

from app.core.config import get_settings
from app.domain.auth.service import AuthService
from app.domain.profile.service import ProfileService
from app.models.profile import ProfileExperience
from app.models.skill import ProfileSkill, Skill
from app.worker.tasks.profile import build_profile


async def test_build_profile_task_writes_profile_skills(db_session, monkeypatch):
    monkeypatch.setattr("app.worker.tasks.profile._session_for", lambda: _ctx(db_session))
    for slug, label in [("python", "Python"), ("fastapi", "FastAPI")]:
        db_session.add(Skill(slug=slug, label=label, category="backend", aliases=[]))
    reg = await AuthService(db_session).register("pt@example.com", "correct-passphrase",
                                                 "P", ip=None, user_agent=None)
    uid = reg.user.id
    profile = await ProfileService(db_session).get_or_create(uid)
    db_session.add(ProfileExperience(user_id=uid, profile_id=profile.id, company="A", title="T",
                                     source="resume_extraction", order_index=0,
                                     tech=["Python", "FastAPI"]))
    await db_session.flush()

    out = await build_profile({}, str(uid))
    assert out["matched"] == 2
    rows = (await db_session.execute(
        select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
    )).scalars().all()
    assert len(rows) == 2
```

> Provide a `_ctx` async-CM helper in the test module that yields the passed session unchanged (same pattern as `tests/worker/test_resume_tasks.py`).

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** `_session_for` in `profile.py` is a verbatim copy of the one in `resume.py` (do not import it — keep the task modules decoupled). Register in `tasks/__init__.py` (`from app.worker.tasks.profile import build_profile`; add to `__all__`) and `main.py` (`from app.worker.tasks import build_profile, extract_resume, parse_resume, ping` + `functions` list). In `resume/service.py`, `enqueue` is already imported (`from app.core.queue import enqueue`); add the one call at the end of `confirm_profile`.

- [ ] **Step 4: Run — expect pass** (DB → CI). Local: `ruff` + `mypy` + `lint-imports` (2 kept) + `"$UV" run pytest --collect-only -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker/tasks/profile.py backend/app/worker/tasks/__init__.py backend/app/worker/main.py backend/app/domain/resume/service.py backend/tests/worker/test_profile_task.py
git commit -m "feat(worker): build_profile task; confirm-profile enqueues it"
```

---

## Task 7: `/profile/skills`, `/profile/rebuild`, strength `dimensions`

**Files:**
- Modify: `backend/app/api/v1/profile.py`, `backend/app/api/v1/schemas/profile.py`
- Test: `backend/tests/api/test_profile_skills.py` (new)

**Interfaces:**
- Consumes: `ProfileService.list_skills` (Task 5); `enqueue`; `compute_strength` with `skill_count`.
- Produces:
  - `schemas/profile.py`:
    - `class StrengthDimensionOut(BaseModel)`: `key: str`, `label: str`, `earned: int`, `max: int`, `hint: str`, `met: bool`.
    - `StrengthOut` gains `dimensions: list[StrengthDimensionOut]`.
    - `class SkillRefOut(BaseModel)`: `kind: str`, `ref_id: uuid.UUID`.
    - `class ProfileSkillOut(BaseModel)`: `slug: str`, `label: str`, `category: str`, `proficiency: str | None`, `years: float | None`, `source: str`, `evidence: list[SkillRefOut]`.
  - `profile.py`:
    - `GET /profile/skills` → `list[ProfileSkillOut]` — `rows = await ProfileService(db).list_skills(user.id)`; map each `(ps, skill)` to `ProfileSkillOut(slug=skill.slug, label=skill.label, category=skill.category, proficiency=ps.proficiency, years=float(ps.years) if ps.years is not None else None, source=ps.source, evidence=[SkillRefOut(**r) for r in ps.evidence_refs])`.
    - `POST /profile/rebuild` → `status_code=202`, body-less: `await enqueue("build_profile", str(user.id))`; return `{"status": "queued"}` (or a small typed model — a `dict[str, str]` return is acceptable here, mirror the résumé 202 routes if they use a model).
    - `get_strength` — after `compute_strength(...)`, also count skills: pass `skill_count=len([r for r in ... ])` — simplest: `_, sections = await ProfileService(db).load_full(user.id)` already runs; add `skills = await ProfileService(db).list_skills(user.id)` and `compute_strength(profile, counts, skill_count=len(skills))`; return `dimensions=[StrengthDimensionOut(**vars(d)) for d in result.dimensions]`.

- [ ] **Step 1: Write the failing test**

`backend/tests/api/test_profile_skills.py` (DB+Redis-backed):

```python
async def _auth(client, email="skapi@example.com"):
    r = await client.post("/api/v1/auth/register",
                          json={"email": email, "password": "correct-passphrase",
                                "full_name": "SK"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_strength_has_dimensions(client):
    h = await _auth(client)
    r = await client.get("/api/v1/profile/strength", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["dimensions"], list)
    assert sum(d["max"] for d in body["dimensions"]) == 100
    assert any(d["key"] == "skills_mapped" for d in body["dimensions"])


async def test_skills_empty_then_rebuild_202(client):
    h = await _auth(client, "skapi2@example.com")
    assert (await client.get("/api/v1/profile/skills", headers=h)).json() == []
    rb = await client.post("/api/v1/profile/rebuild", headers=h)
    assert rb.status_code == 202
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** `mypy` note: `StrengthDimensionOut(**vars(d))` on a frozen dataclass is fine; or add a `.model_validate` path. Keep `enqueue` import at module top of `profile.py` (`from app.core.queue import enqueue`) — `app.api` → `app.core` is allowed.

- [ ] **Step 4: Run — expect pass** (DB+Redis → CI). Local: `ruff` + `mypy` + `lint-imports` + `"$UV" run pytest --collect-only -q` + `"$UV" run python -c "from app.main import create_app; print(sorted(p for p in create_app().openapi()['paths'] if 'profile' in p))"` (with the test env vars) shows `/api/v1/profile/skills` and `/api/v1/profile/rebuild`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/profile.py backend/app/api/v1/schemas/profile.py backend/tests/api/test_profile_skills.py
git commit -m "feat(api): /profile/skills, /profile/rebuild, strength dimensions"
```

---

## Task 8: frontend — types + endpoints + query key

**Files:**
- Modify: `frontend/lib/api/types.ts`, `frontend/lib/api/endpoints.ts`, `frontend/lib/query.ts`
- Test: `frontend/tests/api/endpoints.test.ts` (extend)

**Interfaces — Produces:**
- `types.ts`:
  - `StrengthDimension = { key: string; label: string; earned: number; max: number; hint: string; met: boolean }`.
  - `Strength` gains `dimensions: StrengthDimension[]`.
  - `ProfileSkill = { slug: string; label: string; category: string; proficiency: string | null; years: number | null; source: string; evidence: { kind: string; ref_id: string }[] }`.
- `endpoints.ts` `profile` group gains:
  - `async skills() { return f<ProfileSkill[]>("/api/v1/profile/skills"); }`
  - `async rebuild() { return f<void>("/api/v1/profile/rebuild", { method: "POST" }); }`
- `query.ts` `qk` gains `skills: ["profile", "skills"] as const`.

- [ ] **Step 1: Write the failing test** — append to `frontend/tests/api/endpoints.test.ts`:

```ts
describe("profile skills", () => {
  it("skills GETs /profile/skills", async () => {
    const calls: string[] = [];
    const api = makeApi(async (p) => { calls.push(p); return []; });
    await api.profile.skills();
    expect(calls[0]).toBe("/api/v1/profile/skills");
  });
  it("rebuild POSTs /profile/rebuild", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi(async (path, init) => { calls.push({ path, init }); return undefined; });
    await api.profile.rebuild();
    expect(calls[0].path).toBe("/api/v1/profile/rebuild");
    expect(calls[0].init?.method).toBe("POST");
  });
});
```

- [ ] **Step 2–4:** run → fail → implement → `pnpm exec vitest run tests/api/endpoints.test.ts && pnpm exec tsc --noEmit && pnpm lint`.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/lib/query.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(api): profile skills types + endpoints + query key"
```

---

## Task 9: frontend — `StrengthMeter` per-dimension breakdown

**Files:**
- Modify: `frontend/components/common/StrengthMeter.tsx`
- Test: `frontend/tests/common/strength-meter.test.tsx` (extend)

**Interfaces — Produces:** `StrengthMeter` gains an optional `dimensions?: StrengthDimension[]` prop. When present it renders, under the total bar, a list of dimensions: each shows `label`, a small `earned/max` bar, and — when `!met` — the `hint` prefixed with `△`. The existing `missing`-list rendering is kept as the fallback when `dimensions` is absent. `score` + `missing` props and their existing behaviour are unchanged, so the current tests stay green.

- [ ] **Step 1: Write the failing test** — extend `frontend/tests/common/strength-meter.test.tsx`:

```tsx
it("renders a per-dimension breakdown when dimensions are given", () => {
  render(
    <StrengthMeter
      score={22}
      missing={["x"]}
      dimensions={[
        { key: "experience", label: "Work experience", earned: 16, max: 16, hint: "h", met: true },
        { key: "skills_mapped", label: "Skills mapped", earned: 0, max: 8, hint: "Upload a résumé", met: false },
      ]}
    />,
  );
  expect(screen.getByText("Work experience")).toBeInTheDocument();
  expect(screen.getByText("Skills mapped")).toBeInTheDocument();
  expect(screen.getByText(/upload a résumé/i)).toBeInTheDocument();
});
```

- [ ] **Step 2–4:** run → fail → implement → `pnpm exec vitest run tests/common/strength-meter.test.tsx && pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint` (whole suite — shared component).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/common/StrengthMeter.tsx frontend/tests/common/strength-meter.test.tsx
git commit -m "feat(profile): StrengthMeter per-dimension breakdown"
```

---

## Task 10: frontend — `ProfileSkills` + profile-page wiring

**Files:**
- Create: `frontend/components/profile/ProfileSkills.tsx`
- Modify: `frontend/app/(app)/profile/page.tsx`
- Test: `frontend/tests/profile/profile-skills.test.tsx` (new), `frontend/tests/profile-page.test.tsx` (extend if it stubs `api.profile`)

**Interfaces — Produces:**
- `ProfileSkills()` — a client component. `useQuery({ queryKey: qk.skills, queryFn: () => api.profile.skills() })`. Pending → a `<Skeleton>`; error → a muted "couldn't load your skills" line; empty → an `<EmptyState>`-style line "No skills mapped yet — upload a résumé and we'll pull them in." Otherwise: group the list by `skill.category` (stable category order), render each category as a small heading + a row of skill chips (`label`; a proficiency chip when `proficiency` is set, else nothing; a muted count `"{evidence.length} mentions"` when `evidence.length > 0`; a "from your résumé" tag when `source === "resume_extraction"`). Above the list, a **"Rebuild from résumé"** `<Button variant="outline" size="sm">` → `useMutation(() => api.profile.rebuild())`; `onSuccess` → `toast({ title: "Rebuilding your skills — check back in a moment." })` and `queryClient.invalidateQueries({ queryKey: qk.skills })` + `{ queryKey: qk.strength }`; `onError` → `toast({ title: "Couldn't start a rebuild.", variant: "danger" })`; disabled while pending.
- `profile/page.tsx` — pass `dimensions={strengthQuery.data.dimensions}` to `<StrengthMeter>`; add a `<Card><CardBody><ProfileSkills /></CardBody></Card>` section between the scalar-form card and the sub-entity sections, with an `<h2>Skills</h2>` heading.

- [ ] **Step 1: Write the failing test**

`frontend/tests/profile/profile-skills.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import { ProfileSkills } from "@/components/profile/ProfileSkills";

function api(over = {}) {
  return {
    profile: {
      skills: vi.fn(async () => [
        { slug: "pytorch", label: "PyTorch", category: "ml_framework",
          proficiency: null, years: null, source: "resume_extraction",
          evidence: [{ kind: "experience", ref_id: "e1" }, { kind: "project", ref_id: "p1" }] },
        { slug: "fastapi", label: "FastAPI", category: "backend",
          proficiency: "advanced", years: 3, source: "user", evidence: [] },
      ]),
      rebuild: vi.fn(async () => undefined),
      ...over,
    },
  };
}

describe("ProfileSkills", () => {
  it("groups skills and shows evidence counts", async () => {
    renderWithProviders(<ProfileSkills />, { api: api() });
    expect(await screen.findByText("PyTorch")).toBeInTheDocument();
    expect(screen.getByText("FastAPI")).toBeInTheDocument();
    expect(screen.getByText(/2 mentions/i)).toBeInTheDocument();
  });

  it("Rebuild from résumé calls the endpoint", async () => {
    const a = api();
    renderWithProviders(<ProfileSkills />, { api: a });
    await screen.findByText("PyTorch");
    await userEvent.click(screen.getByRole("button", { name: /rebuild from résumé/i }));
    await waitFor(() => expect(a.profile.rebuild).toHaveBeenCalledTimes(1));
  });

  it("empty state prompts a résumé upload", async () => {
    renderWithProviders(<ProfileSkills />, { api: api({ skills: vi.fn(async () => []) }) });
    expect(await screen.findByText(/no skills mapped yet/i)).toBeInTheDocument();
  });
});
```

If `frontend/tests/profile-page.test.tsx` stubs `api.profile`, add `skills: vi.fn(async () => [])` + `rebuild: vi.fn()` to that stub and (if it asserts on strength) a `dimensions: []` on the strength stub so the page renders.

- [ ] **Step 2–4:** run → fail → implement → `pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint` (whole suite — the profile page is shared).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/profile/ProfileSkills.tsx "frontend/app/(app)/profile/page.tsx" frontend/tests/profile/profile-skills.test.tsx frontend/tests/profile-page.test.tsx
git commit -m "feat(profile): Skills section on /profile with rebuild"
```

---

## Task 11: Phase 3 verification & completion report

- [ ] **Step 1: Full backend gate** — `cd backend && "$UV" run ruff check . && "$UV" run lint-imports && "$UV" run mypy app && "$UV" run pytest -q` — ruff clean; 2 import contracts kept; mypy clean; pytest green (Phases 0–3), coverage ≥ CI floor. (DB/Redis suites verify in CI; locally confirm `--collect-only` is error-free and the non-DB tests pass.)
- [ ] **Step 2: Seed smoke** — `cd backend && "$UV" run python -m app.seed skills` against the CI database (or document "not run — no local DB"); confirm it prints a count ≥ 150 and is idempotent on a second run. Add a CI step or a DB test (`tests/domain/skills/test_seed.py`) that runs `seed_skills()` once and asserts `SELECT count(*) FROM skills >= 150` and that every row has a non-null `embedding`.
- [ ] **Step 3: Full frontend gate** — `cd frontend && pnpm lint && pnpm exec tsc --noEmit && pnpm exec vitest run` — all green.
- [ ] **Step 4: OpenAPI sanity** — the `/api/v1/profile/skills` and `/api/v1/profile/rebuild` paths are present.
- [ ] **Step 5: Fill the completion report below, commit** `docs: Phase 3 completion report`.

---

## Phase 3 completion report

_Executed 2026-09-01 (11 tasks). Ledger: `.superpowers/sdd/2026-09-01-phase-3-career-profile/`._

- **What changed:**
  - **Migration `0006_skills`** (`alembic/versions/0006_skills.py`, `app/models/skill.py`) — `skills` taxonomy table (`slug` unique, `label`, `category`, `aliases[]`, pgvector `embedding`) + `profile_skills` link table (`(profile_id, skill_id)` unique, `source`, `proficiency`, `years`, `evidence_refs` JSONB). Chain `0005_resumes → 0006_skills`, linear.
  - **Skill taxonomy + seed** (`app/domain/skills/taxonomy.json`, `app/seed.py`) — 198 curated entries across 11 categories; `python -m app.seed skills` upserts them on `slug` with embeddings. `seed_skills()` now takes an optional `session=` (flush, no commit) for test isolation; the no-arg CLI path is unchanged.
  - **`SkillNormalizer`** (`app/domain/skills/normalizer.py`) — exact/alias match, then pgvector cosine near-match above `threshold=0.82`; `normalize` / `normalize_many` return `SkillMatch {skill_id, slug, label, method, score}`.
  - **`ProfileBuilder`** (`app/domain/profile/builder.py`) — maps the `tech[]` on experiences + projects plus the primary extracted résumé's `skills[]` onto the taxonomy, writes `source="resume_extraction"` `profile_skills` rows with evidence refs, skips any skill that already has a `source="user"` row; returns `BuildResult {matched, evidence_total, unmatched}`.
  - **Strength breakdown** (`app/domain/profile/strength.py`, `service.py`) — `compute_strength(profile, counts, *, skill_count=0)` now returns per-dimension `StrengthDimension {key, label, earned, max, hint, met}` and adds a `skills_mapped` dimension (met at `skill_count >= 5`); `ProfileService._recompute` passes the live skill count.
  - **`build_profile` worker task** (`app/worker/tasks/profile.py`, `worker/main.py`, `worker/tasks/__init__.py`) — ARQ task that runs the builder in its own session; `confirm_profile` (`domain/resume/service.py`) enqueues `build_profile` after a résumé is confirmed.
  - **API** (`app/api/v1/profile.py`, `app/api/v1/schemas/profile.py`) — `GET /profile/skills` (grouped `ProfileSkillOut {slug, label, category, proficiency, years, source, evidence:[{kind, ref_id}]}`), `POST /profile/rebuild` (202, fire-and-forget enqueue), and `dimensions[]` added to the strength payload.
  - **Frontend** — `StrengthMeter` per-dimension breakdown (`components/common/StrengthMeter.tsx`), `ProfileSkills` section on `/profile` with a Rebuild button (`components/profile/ProfileSkills.tsx`, `app/(app)/profile/page.tsx`), `lib/api/types.ts` (+`ProfileSkill` / `StrengthDimension`), `lib/api/endpoints.ts` (+`api.profile.skills` / `api.profile.rebuild`), `lib/query.ts` (+`qk.skills`).
- **Why:** a clean, taxonomy-mapped skill set with evidence is what Phase 5 matching scores against and Phase 12 insights aggregate; the strength breakdown makes the score actionable.
- **Files changed / new deps:** ~24 backend files (7 new source: `models/skill.py`, `alembic/versions/0006_skills.py`, `domain/skills/{__init__,normalizer}.py`, `domain/skills/taxonomy.json`, `domain/profile/builder.py`, `worker/tasks/profile.py`; edits to `app/seed.py`, `domain/profile/{strength,service}.py`, `domain/resume/service.py`, `api/v1/profile.py`, `api/v1/schemas/profile.py`, `worker/main.py`, `worker/tasks/__init__.py`, `models/__init__.py`; 8 test files incl. new `tests/domain/skills/{test_taxonomy,test_normalizer,test_seed}.py`, `tests/models/test_skill_model.py`, `tests/domain/profile/test_builder.py`, `tests/worker/test_profile_task.py`, `tests/api/test_profile_skills.py`) + ~10 frontend files (`components/common/StrengthMeter.tsx`, `components/profile/ProfileSkills.tsx`, `app/(app)/profile/page.tsx`, `lib/api/{types,endpoints}.ts`, `lib/query.ts`, + `tests/{api/endpoints,common/strength-meter,profile-page,profile/profile-skills}.test.tsx`). **No new dependencies** — pgvector, `EmbeddingsProvider` (fake in CI), and ARQ were all already present.
- **How to test:** `cd backend && uv run pytest tests/domain/skills tests/domain/profile/test_builder.py tests/worker/test_profile_task.py tests/api/test_profile_skills.py -q` · `cd frontend && pnpm exec vitest run`.
- **Regression check:** Phases 0–2b suites green; migration chain `0001 → … → 0006` linear; `/auth`, `/resumes`, existing `/profile` routes unchanged bar the added `dimensions` field; `import-linter` — 2 contracts kept; `ruff` / `mypy app` (71 source files) clean; frontend `tsc --noEmit` + `next lint` clean.
- **Baseline:** 162 backend tests → 180 (`pytest --collect-only`, no collection errors); 29 frontend files / 73 tests → 30 files / 79 tests (`vitest run`, all green).
- **Deviations:**
  - LLM-based normalization and proficiency/years inference **deferred** (Global Constraints) — normalization is deterministic exact/alias + embedding; proficiency/years stay null until a later phase.
  - Résumé `skills[]` **included** — sourced from the primary extracted résumé only, not free-text description mining.
  - Résumé Workspace 3-pane shell **deferred to Phase 8** (nothing to render until versions/diff/suggestions exist).
  - `seed_skills()` gained an optional `session=` parameter for test isolation (controller ruling) — with no arg it still opens its own `AsyncSessionLocal` and commits.
- **Not verified here:** real embedding-provider near-match quality (fake provider only exercises the exact-string path); `resume_chunks`-level evidence (Phase 6); proficiency/years inference (later); the Résumé Workspace shell (Phase 8). DB/Redis-backed suites (models, normalizer, builder, profile service, worker task, API, `test_seed.py`) verify in CI — locally only `--collect-only` and the no-DB `tests/domain/skills/test_taxonomy.py` (2 passed) were run.

---

## Self-Review

**1. Spec coverage (Phase 3 of §9 + §2.2 `skills/`/`profile/` + §4.3 `profile_builder` + §5.3 tables):**
- `profile_builder` normalization → Tasks 4 (`ProfileBuilder`) + 6 (`build_profile` task). ✓ (deterministic; LLM-normalize deferred, flagged.)
- skill taxonomy + alias normalization → Tasks 1 (`skills` table), 2 (taxonomy + seed), 3 (`SkillNormalizer` exact/alias + embedding). ✓
- evidence linking → Task 1 (`profile_skills.evidence_refs`) + Task 4 (populated from experience/project/resume ids). ✓ (chunk-level refs are Phase 6, flagged.)
- strength breakdown → Task 5 (`StrengthDimension` + `skills_mapped`) + Task 7 (`dimensions` on the API) + Task 9 (UI). ✓
- Résumé Workspace 3-pane shell → **deferred to Phase 8** (Global Constraints + design decision — nothing to render until versions/diff/suggestions exist). ✓
- "Done when: manual + résumé-derived profile coexist; skills map to taxonomy" → `profile_skills.source` distinguishes them; Task 4's idempotency test asserts a `source="user"` row survives a rebuild. ✓

**2. Placeholder scan:** Tasks 1–3, 5, 8, 9 carry literal code + tests. Tasks 4, 6, 7, 10 carry full Produces contracts + concrete tests and describe the bodies against them (accepted style, Phases 2a/2b). One deliberate seam is named: `_session_for` in Task 6 (verbatim copy from `resume.py`), monkeypatched in the test. The embedding-path test in Task 3 spells out the fake-provider trick (embed and query the same string). No "TBD".

**3. Type consistency:**
- `Skill` / `ProfileSkill` (Task 1) consumed by Tasks 3, 4, 5, 7 under the same field names.
- `SkillMatch` (Task 3) — `{skill_id, slug, label, method, score}` — consumed only by Task 4.
- `BuildResult` (Task 4) — `{matched, evidence_total, unmatched}` — consumed by Task 6's task return + Task 11.
- `StrengthDimension` (Task 5) — `{key, label, earned, max, hint, met}` — mirrored exactly by `StrengthDimensionOut` (Task 7) and the frontend `StrengthDimension` type (Task 8) and rendered by Task 9.
- `ProfileSkillOut` (Task 7) — `{slug, label, category, proficiency, years, source, evidence: [{kind, ref_id}]}` — mirrored by the frontend `ProfileSkill` type (Task 8) and consumed by Task 10.
- `compute_strength(profile, counts, *, skill_count=0)` (Task 5) — the new kw-only arg is passed by `ProfileService._recompute` (Task 5) and the `/profile/strength` route (Task 7); all other callers keep the default.
- `enqueue("build_profile", str(user_id))` — Task 6 registers the task name; Task 6 (`confirm_profile`) and Task 7 (`POST /profile/rebuild`) both call it with a single str arg.
- Migration chain `0005_resumes` → `0006_skills`. ✓

**4. Ambiguity check:** `profile_skills` rows written by the builder are always `source="resume_extraction"`; a skill that already has a `source="user"` row is skipped (the `(profile_id, skill_id)` unique constraint forces this — Task 4 design note + test). `skills_mapped` strength dimension is met at `skill_count >= 5`. The builder's skill inputs are the `tech[]` arrays on experiences+projects plus the *primary extracted* résumé's `skills[]` — not free-text description mining. Unmatched raw strings are dropped (returned in `BuildResult.unmatched` and emitted on the `build_profile` task's `log.info("profile_built", …)` line), never invented into the taxonomy. `POST /profile/rebuild` is fire-and-forget (202) — the UI tells the user to check back; it does not stream progress.

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-09-01-phase-3-career-profile.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between, whole-branch review at the end.

**2. Inline Execution** — `superpowers:executing-plans`, batched with checkpoints.

**Environment:** `uv` installed (path in Tech Stack); backend `ruff`/`mypy`/`import-linter` + non-DB tests run locally, DB+Redis-backed tests (Tasks 1, 3, 4, 5-service, 6, 7) verify in CI. Frontend runs fully locally with `pnpm exec vitest run`. The skill-embedding near-match path is only meaningfully exercised with a real `EmbeddingsProvider` (Phase 6) — CI covers the exact/alias path and a same-string embedding round-trip.
