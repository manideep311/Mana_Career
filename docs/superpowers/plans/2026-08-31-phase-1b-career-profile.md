# Phase 1b — Career Profile (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** An authenticated user can describe their career: one `career_profiles` row (auto-created on first read) with contact links, job preferences, salary expectations, seniority and goals; plus ordered lists of `experiences`, `education`, `projects`, and `certifications`. Every read/write is scoped to the current user. A deterministic **profile-strength** score (0–100) with a per-section completeness map and a "what's missing" list is recomputed on every mutation and stored on the profile for cheap dashboard reads.

**Architecture:** New `app/domain/profile/` package — `service.py` (`ProfileService`: get-or-create, scalar update, generic sub-entity CRUD + reorder, strength recompute) and `strength.py` (pure `compute_strength`). Router `app/api/v1/profile.py` with a small **generic sub-entity router factory** so the four near-identical resources share one implementation. All mutations recompute strength and write an `audit_logs` row. Consumes `get_current_user` / `CurrentUser` from Phase 1a.

**Out of scope for 1b (deferred to Phase 3 — "Career profile generation"):** the `skills` taxonomy table, `profile_skills`, alias normalization, `/profile/skills`, `GET /api/v1/skills?query=`, and résumé-extraction `source` population. 1b ships the structured profile a human fills in by hand; Phase 3 adds skills + normalization + evidence linking.

**Tech Stack:** unchanged from Phase 1a — Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, pytest + httpx `ASGITransport`. Local checks via `backend/.venv/Scripts/` (ruff, mypy, lint-imports, pytest); DB-backed tests need Postgres 16 + pgvector + Redis 7 (Docker Compose or CI).

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` — implements the profile slice of §9 Phase 1, §1.4 (strength as a deterministic score), §5.3 "Career profile" tables, §6.2 `/profile`. Phase 1 "done when": *login → profile editable → strength shown* (auth half done in Phase 1a).

## Global Constraints

Same as Phase 1a's Global Constraints section (uuid PKs `gen_random_uuid()`; `timestamptz` + `set_updated_at` trigger; `text`+`CHECK` enums; per-user isolation; `problem+json` + stable `code`; append-only `audit_logs` via the one `audit()` helper; import-linter layers `api > worker > domain > core > models`; TDD, commit per green step). Additionally:

- **One profile per user.** `career_profiles.user_id` is a `UNIQUE NOT NULL` FK to `users.id` `ON DELETE CASCADE`. `GET /profile` lazily creates the row; it is never returned as 404.
- **Sub-entity isolation.** Every sub-entity row carries `user_id NOT NULL` (FK `users`, `ON DELETE CASCADE`) *and* `profile_id NOT NULL` (FK `career_profiles`, `ON DELETE CASCADE`). All queries filter by `user_id = current_user.id`.
- **Strength is derived, never client-set.** `profile_strength` + `completeness` are recomputed from the DB by `ProfileService` after every mutation. The `PUT`/`POST`/`PATCH`/`DELETE`/reorder responses reflect the fresh value.
- **`source`** on every sub-entity is `text NOT NULL DEFAULT 'user'`, `CHECK IN ('user','resume_extraction')`. 1b only ever writes `'user'`.

---

## File Structure

**Created**
- `backend/app/models/profile.py` — `CareerProfile`, `ProfileExperience`, `ProfileEducation`, `ProfileProject`, `ProfileCertification`.
- `backend/alembic/versions/0004_career_profiles.py` — the five tables + indexes + CHECKs + `updated_at` triggers.
- `backend/app/domain/profile/__init__.py` — empty.
- `backend/app/domain/profile/strength.py` — pure `compute_strength(...)` + `StrengthResult`.
- `backend/app/domain/profile/service.py` — `ProfileService`.
- `backend/app/api/v1/schemas/profile.py` — request/response models + the sub-entity schema registry.
- `backend/app/api/v1/profile.py` — the `/profile` router + `_make_subentity_router(...)` factory.
- Tests: `backend/tests/models/test_profile_models.py`, `backend/tests/domain/profile/test_strength.py`, `backend/tests/domain/profile/test_service.py`, `backend/tests/api/test_profile.py`, `backend/tests/api/test_profile_subentities.py`.

**Modified**
- `backend/app/models/__init__.py` — import `profile`.
- `backend/app/api/v1/router.py` — include the profile router.

---

## Task 1: Profile ORM models + migration `0004`

**Files:**
- Create: `backend/app/models/profile.py`
- Create: `backend/alembic/versions/0004_career_profiles.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/test_profile_models.py`

**Interfaces — Produces:**
- `app.models.profile.CareerProfile` — `id` · `user_id` (UUID, FK `users.id` CASCADE, **unique**, not null) · `location: str|None` · `github_url/linkedin_url/portfolio_url: str|None` · `preferred_roles: list[str]` (`ARRAY(Text)`, server default `'{}'`) · `preferred_locations: list[str]` · `work_modes: list[str]` · `expected_salary_min/max: int|None` · `salary_currency: str|None` · `salary_period: str|None` (CHECK `in ('year','month')`) · `years_experience: Decimal|None` (`Numeric(4,1)`) · `seniority: str|None` (CHECK `in ('junior','mid','senior','staff','lead','principal')`) · `career_goals: str|None` · `profile_strength: int` (not null, server default `0`) · `completeness: dict` (`JSONB`, server default `'{}'`) · `created_at`/`updated_at`.
- `ProfileExperience` — common cols (`id`, `user_id` FK CASCADE not null, `profile_id` FK `career_profiles.id` CASCADE not null, `source` str not null default `'user'` CHECK `in ('user','resume_extraction')`, `order_index` int not null default `0`, ts) **plus** `company: str` (not null) · `title: str` (not null) · `employment_type: str|None` · `start_date/end_date: date|None` · `is_current: bool` (not null, default `false`) · `location: str|None` · `description: str|None` · `highlights: list[str]` · `tech: list[str]`.
- `ProfileEducation` — common cols **plus** `institution: str` (not null) · `degree: str|None` · `field: str|None` · `start_date/end_date: date|None` · `grade: str|None`.
- `ProfileProject` — common cols **plus** `name: str` (not null) · `description: str|None` · `url: str|None` · `highlights: list[str]` · `tech: list[str]` · `start_date/end_date: date|None`.
- `ProfileCertification` — common cols **plus** `name: str` (not null) · `issuer: str|None` · `issued_date/expires_date: date|None` · `credential_id: str|None` · `url: str|None`.
- Migration `0004_career_profiles` (`down_revision = "0003_users"`): the five `CREATE TABLE`s, `uq_career_profiles_user_id`, an index `ix_<t>_profile_id` on each sub-entity, the CHECKs, and `CREATE TRIGGER trg_<t>_set_updated_at BEFORE UPDATE ... EXECUTE FUNCTION set_updated_at()` for all five.

- [ ] **Step 1: Write the failing test**

`backend/tests/models/test_profile_models.py`:

```python
import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.profile import (
    CareerProfile,
    ProfileCertification,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
)
from app.models.user import User


async def _user(db_session, email="p@example.com") -> User:
    u = User(email=email, password_hash="x", full_name="P")
    db_session.add(u)
    await db_session.flush()
    return u


async def _profile(db_session, user: User) -> CareerProfile:
    p = CareerProfile(user_id=user.id)
    db_session.add(p)
    await db_session.flush()
    return p


async def test_profile_defaults(db_session):
    u = await _user(db_session)
    p = await _profile(db_session, u)
    got = (await db_session.execute(
        select(CareerProfile).where(CareerProfile.id == p.id)
    )).scalar_one()
    assert got.profile_strength == 0
    assert got.completeness == {}
    assert got.preferred_roles == []


async def test_one_profile_per_user(db_session):
    u = await _user(db_session, "one@example.com")
    await _profile(db_session, u)
    with pytest.raises(IntegrityError):
        await _profile(db_session, u)


async def test_salary_period_check(db_session):
    u = await _user(db_session, "sal@example.com")
    p = await _profile(db_session, u)
    p.salary_period = "fortnight"
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (ProfileExperience, {"company": "Acme", "title": "Eng"}),
        (ProfileEducation, {"institution": "Uni"}),
        (ProfileProject, {"name": "RAG thing"}),
        (ProfileCertification, {"name": "AWS SAA"}),
    ],
)
async def test_subentity_round_trip_and_cascade(db_session, model, kwargs):
    u = await _user(db_session, f"{model.__name__.lower()}@example.com")
    p = await _profile(db_session, u)
    row = model(user_id=u.id, profile_id=p.id, **kwargs)
    db_session.add(row)
    await db_session.flush()
    assert row.source == "user"
    assert row.order_index == 0
    await db_session.delete(p)
    await db_session.flush()
    gone = (await db_session.execute(select(model).where(model.id == row.id))).first()
    assert gone is None


async def test_experience_is_current_default_false(db_session):
    u = await _user(db_session, "cur@example.com")
    p = await _profile(db_session, u)
    e = ProfileExperience(user_id=u.id, profile_id=p.id, company="A", title="B",
                          start_date=dt.date(2020, 1, 1))
    db_session.add(e)
    await db_session.flush()
    assert e.is_current is False
    assert e.highlights == [] and e.tech == []
```

- [ ] **Step 2: Run — expect fail** (`ModuleNotFoundError: app.models.profile`).

Run: `cd backend && uv run pytest tests/models/test_profile_models.py -q`

- [ ] **Step 3: Implement**

`backend/app/models/profile.py`:

```python
from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric,
    String, Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_SENIORITY = "seniority in ('junior','mid','senior','staff','lead','principal')"
_SALARY_PERIOD = "salary_period in ('year','month')"
_SOURCE = "source in ('user','resume_extraction')"


class CareerProfile(Base, TimestampMixin):
    __tablename__ = "career_profiles"
    __table_args__ = (
        CheckConstraint(_SENIORITY, name="career_profile_seniority_valid"),
        CheckConstraint(_SALARY_PERIOD, name="career_profile_salary_period_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    location: Mapped[str | None] = mapped_column(String(200))
    github_url: Mapped[str | None] = mapped_column(String(300))
    linkedin_url: Mapped[str | None] = mapped_column(String(300))
    portfolio_url: Mapped[str | None] = mapped_column(String(300))
    preferred_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    preferred_locations: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    work_modes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    expected_salary_min: Mapped[int | None] = mapped_column(Integer)
    expected_salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(8))
    years_experience: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 1))
    seniority: Mapped[str | None] = mapped_column(String(16))
    career_goals: Mapped[str | None] = mapped_column(Text)
    profile_strength: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completeness: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class _SubEntity(TimestampMixin):
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("career_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'user'")
    )
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class ProfileExperience(_SubEntity, Base):
    __tablename__ = "profile_experiences"
    __table_args__ = (
        CheckConstraint(_SOURCE, name="profile_experience_source_valid"),
        Index("ix_profile_experiences_profile_id", "profile_id"),
    )
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(40))
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    location: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    highlights: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    tech: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )


class ProfileEducation(_SubEntity, Base):
    __tablename__ = "profile_education"
    __table_args__ = (
        CheckConstraint(_SOURCE, name="profile_education_source_valid"),
        Index("ix_profile_education_profile_id", "profile_id"),
    )
    institution: Mapped[str] = mapped_column(String(200), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(200))
    field: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    grade: Mapped[str | None] = mapped_column(String(80))


class ProfileProject(_SubEntity, Base):
    __tablename__ = "profile_projects"
    __table_args__ = (
        CheckConstraint(_SOURCE, name="profile_project_source_valid"),
        Index("ix_profile_projects_profile_id", "profile_id"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(300))
    highlights: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    tech: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)


class ProfileCertification(_SubEntity, Base):
    __tablename__ = "profile_certifications"
    __table_args__ = (
        CheckConstraint(_SOURCE, name="profile_certification_source_valid"),
        Index("ix_profile_certifications_profile_id", "profile_id"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(200))
    issued_date: Mapped[dt.date | None] = mapped_column(Date)
    expires_date: Mapped[dt.date | None] = mapped_column(Date)
    credential_id: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(300))
```

> **Note on `_SubEntity`:** it is a plain mixin (NOT a mapped class) so the four tables each get their own columns. `TimestampMixin` must come before `Base` in the MRO for the four concrete classes — hence `class ProfileExperience(_SubEntity, Base)`.

`backend/app/models/__init__.py` — add `from app.models import profile as profile` next to the others.

`backend/alembic/versions/0004_career_profiles.py`:

```python
"""career_profiles and sub-entities

Revision ID: 0004_career_profiles
Revises: 0003_users
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004_career_profiles"
down_revision = "0003_users"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")
_ARR = pg.ARRAY(sa.Text())
_EMPTY = sa.text("'{}'")


def _common() -> list[sa.Column]:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'user'")),
        sa.Column("order_index", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
    ]


def upgrade() -> None:
    op.create_table(
        "career_profiles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location", sa.String(200)),
        sa.Column("github_url", sa.String(300)),
        sa.Column("linkedin_url", sa.String(300)),
        sa.Column("portfolio_url", sa.String(300)),
        sa.Column("preferred_roles", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("preferred_locations", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("work_modes", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("expected_salary_min", sa.Integer),
        sa.Column("expected_salary_max", sa.Integer),
        sa.Column("salary_currency", sa.String(3)),
        sa.Column("salary_period", sa.String(8)),
        sa.Column("years_experience", sa.Numeric(4, 1)),
        sa.Column("seniority", sa.String(16)),
        sa.Column("career_goals", sa.Text),
        sa.Column("profile_strength", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("completeness", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.UniqueConstraint("user_id", name="uq_career_profiles_user_id"),
        sa.CheckConstraint(
            "seniority in ('junior','mid','senior','staff','lead','principal')",
            name="career_profile_seniority_valid",
        ),
        sa.CheckConstraint("salary_period in ('year','month')",
                           name="career_profile_salary_period_valid"),
    )

    experiences_extra = [
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("employment_type", sa.String(40)),
        sa.Column("start_date", sa.Date), sa.Column("end_date", sa.Date),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("location", sa.String(200)),
        sa.Column("description", sa.Text),
        sa.Column("highlights", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("tech", _ARR, nullable=False, server_default=_EMPTY),
    ]
    education_extra = [
        sa.Column("institution", sa.String(200), nullable=False),
        sa.Column("degree", sa.String(200)), sa.Column("field", sa.String(200)),
        sa.Column("start_date", sa.Date), sa.Column("end_date", sa.Date),
        sa.Column("grade", sa.String(80)),
    ]
    projects_extra = [
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text), sa.Column("url", sa.String(300)),
        sa.Column("highlights", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("tech", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("start_date", sa.Date), sa.Column("end_date", sa.Date),
    ]
    certifications_extra = [
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("issuer", sa.String(200)),
        sa.Column("issued_date", sa.Date), sa.Column("expires_date", sa.Date),
        sa.Column("credential_id", sa.String(200)), sa.Column("url", sa.String(300)),
    ]
    for tbl, extra in [
        ("profile_experiences", experiences_extra),
        ("profile_education", education_extra),
        ("profile_projects", projects_extra),
        ("profile_certifications", certifications_extra),
    ]:
        singular = {
            "profile_experiences": "profile_experience",
            "profile_education": "profile_education",
            "profile_projects": "profile_project",
            "profile_certifications": "profile_certification",
        }[tbl]
        op.create_table(
            tbl, *_common(), *extra,
            sa.CheckConstraint("source in ('user','resume_extraction')",
                               name=f"{singular}_source_valid"),
        )
        op.create_index(f"ix_{tbl}_profile_id", tbl, ["profile_id"])

    for tbl in ("career_profiles", "profile_experiences", "profile_education",
                "profile_projects", "profile_certifications"):
        op.execute(
            f"CREATE TRIGGER trg_{tbl}_set_updated_at BEFORE UPDATE ON {tbl} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for tbl in ("profile_certifications", "profile_projects", "profile_education",
                "profile_experiences", "career_profiles"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tbl}_set_updated_at ON {tbl}")
        op.drop_table(tbl)
```

- [ ] **Step 4: Run — expect pass** (DB-backed → run once Postgres is up; otherwise confirm `alembic history` is linear + `Base.metadata.tables` lists all five, + `ruff`/`mypy`).

Run: `cd backend && uv run alembic upgrade head && uv run pytest tests/models/test_profile_models.py -q && uv run ruff check . && uv run mypy app`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/profile.py backend/app/models/__init__.py backend/alembic/versions/0004_career_profiles.py backend/tests/models/test_profile_models.py
git commit -m "feat(models): career_profiles + experience/education/project/certification sub-entities"
```

---

## Task 2: Profile-strength scorer (`app/domain/profile/strength.py`)

**Files:**
- Create: `backend/app/domain/profile/__init__.py` (empty)
- Create: `backend/app/domain/profile/strength.py`
- Test: `backend/tests/domain/profile/test_strength.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) StrengthResult` — `score: int` (0–100), `completeness: dict[str, bool]`, `missing: list[str]`.
- `@dataclass(frozen=True) ProfileCounts` — `experiences: int`, `education: int`, `projects: int`, `certifications: int`.
- `compute_strength(profile: CareerProfile, counts: ProfileCounts) -> StrengthResult` — pure. Weighted checklist summing to 100:

  | key | weight | true when |
  |---|---|---|
  | `location` | 8 | `profile.location` non-empty |
  | `links` | 10 | any of github/linkedin/portfolio url set |
  | `goals` | 10 | `career_goals` non-empty |
  | `preferred_roles` | 8 | `preferred_roles` non-empty |
  | `seniority` | 6 | `seniority` set |
  | `years_experience` | 6 | `years_experience` not None |
  | `salary` | 6 | `expected_salary_min` or `_max` set |
  | `experience` | 20 | `counts.experiences >= 1` |
  | `education` | 12 | `counts.education >= 1` |
  | `projects` | 10 | `counts.projects >= 1` |
  | `certifications` | 4 | `counts.certifications >= 1` |

  `score` = sum of weights whose key is true (already 0–100). `missing` = human labels for false keys, in table order (`{"location": "Add your location", "links": "Add a GitHub, LinkedIn or portfolio link", ...}`).

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/profile/test_strength.py`:

```python
import decimal

from app.domain.profile.strength import ProfileCounts, compute_strength
from app.models.profile import CareerProfile

_ZERO = ProfileCounts(0, 0, 0, 0)
_FULL = ProfileCounts(2, 1, 3, 1)


def _full_profile() -> CareerProfile:
    return CareerProfile(
        user_id=None, location="Hyderabad",
        github_url="https://github.com/x", linkedin_url=None, portfolio_url=None,
        preferred_roles=["AI/ML Engineer"], work_modes=["remote"],
        expected_salary_min=100, expected_salary_max=None, salary_currency="USD",
        years_experience=decimal.Decimal("5.0"), seniority="senior",
        career_goals="Lead an applied-AI team.",
    )


def test_empty_profile_scores_zero():
    r = compute_strength(CareerProfile(user_id=None), _ZERO)
    assert r.score == 0
    assert r.completeness["experience"] is False
    assert "Add your work experience" in r.missing


def test_full_profile_scores_100():
    r = compute_strength(_full_profile(), _FULL)
    assert r.score == 100
    assert r.missing == []
    assert all(r.completeness.values())


def test_partial_profile_sums_weights():
    p = CareerProfile(user_id=None, location="Berlin", career_goals="Ship models.")
    r = compute_strength(p, ProfileCounts(experiences=1, education=0, projects=0,
                                          certifications=0))
    # location 8 + goals 10 + experience 20
    assert r.score == 38
    assert r.completeness["education"] is False


def test_links_true_if_any_url_present():
    p = CareerProfile(user_id=None, portfolio_url="https://me.dev")
    r = compute_strength(p, _ZERO)
    assert r.completeness["links"] is True
    assert r.score == 10
```

- [ ] **Step 2: Run — expect fail** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`backend/app/domain/profile/strength.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.models.profile import CareerProfile

_WEIGHTS: list[tuple[str, int, str]] = [
    ("location", 8, "Add your location"),
    ("links", 10, "Add a GitHub, LinkedIn or portfolio link"),
    ("goals", 10, "Add your career goals"),
    ("preferred_roles", 8, "Add the roles you're targeting"),
    ("seniority", 6, "Set your seniority level"),
    ("years_experience", 6, "Add your years of experience"),
    ("salary", 6, "Add your salary expectations"),
    ("experience", 20, "Add your work experience"),
    ("education", 12, "Add your education"),
    ("projects", 10, "Add a project"),
    ("certifications", 4, "Add a certification"),
]


@dataclass(frozen=True)
class ProfileCounts:
    experiences: int
    education: int
    projects: int
    certifications: int


@dataclass(frozen=True)
class StrengthResult:
    score: int
    completeness: dict[str, bool]
    missing: list[str]


def _truthy(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return True


def compute_strength(profile: CareerProfile, counts: ProfileCounts) -> StrengthResult:
    checks: dict[str, bool] = {
        "location": _truthy(profile.location),
        "links": any(_truthy(u) for u in (
            profile.github_url, profile.linkedin_url, profile.portfolio_url)),
        "goals": _truthy(profile.career_goals),
        "preferred_roles": _truthy(profile.preferred_roles),
        "seniority": _truthy(profile.seniority),
        "years_experience": profile.years_experience is not None,
        "salary": profile.expected_salary_min is not None
        or profile.expected_salary_max is not None,
        "experience": counts.experiences >= 1,
        "education": counts.education >= 1,
        "projects": counts.projects >= 1,
        "certifications": counts.certifications >= 1,
    }
    score = sum(w for key, w, _ in _WEIGHTS if checks[key])
    missing = [label for key, _, label in _WEIGHTS if not checks[key]]
    return StrengthResult(score=score, completeness=checks, missing=missing)
```

- [ ] **Step 4: Run — expect pass** (pure, runs locally).

Run: `cd backend && uv run pytest tests/domain/profile/test_strength.py -q && uv run ruff check . && uv run mypy app`

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/profile/__init__.py backend/app/domain/profile/strength.py backend/tests/domain/profile/test_strength.py
git commit -m "feat(profile): deterministic profile-strength scorer"
```

---

## Task 3: `ProfileService` (`app/domain/profile/service.py`)

**Files:**
- Create: `backend/app/domain/profile/service.py`
- Test: `backend/tests/domain/profile/test_service.py`

**Interfaces — Produces (`app.domain.profile.service`):**
- `SUBENTITY_MODELS: dict[str, type]` — `{"experiences": ProfileExperience, "education": ProfileEducation, "projects": ProfileProject, "certifications": ProfileCertification}`.
- `class ProfileService`:
  - `__init__(self, session: AsyncSession)`
  - `async get_or_create(self, user_id: uuid.UUID) -> CareerProfile` — returns the user's profile, creating an empty one (with a freshly computed strength) on first call.
  - `async load_full(self, user_id: uuid.UUID) -> tuple[CareerProfile, dict[str, list]]` — profile + `{section: [rows ordered by order_index, id]}` for all four sections.
  - `async update_scalars(self, user_id: uuid.UUID, patch: dict) -> CareerProfile` — set only provided keys (whitelist to the scalar/array columns), then `_recompute`.
  - `async list_section(self, user_id, section: str) -> list` — ordered.
  - `async add_item(self, user_id, section: str, data: dict) -> object` — `order_index` = current count; `_recompute`.
  - `async update_item(self, user_id, section: str, item_id: uuid.UUID, patch: dict) -> object` — `NotFoundError` if not the user's; `_recompute`.
  - `async delete_item(self, user_id, section: str, item_id: uuid.UUID) -> None` — `NotFoundError` if not the user's; `_recompute`.
  - `async reorder(self, user_id, section: str, ordered_ids: list[uuid.UUID]) -> list` — every id must belong to the user's profile and the set must match exactly (`ValidationAppError` otherwise); assigns `order_index` by position; `_recompute` (order doesn't change strength but keeps one write path).
  - private `async _recompute(self, profile: CareerProfile) -> None` — counts each section, calls `compute_strength`, writes `profile.profile_strength` + `profile.completeness`.
- All mutating methods write an `audit_logs` row via `audit(...)` (`profile.update` for scalars; `profile.<section_singular>.<op>` for items) with `request_id=current_request_id()`.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/profile/test_service.py`:

```python
import uuid

import pytest

from app.core.errors import NotFoundError, ValidationAppError
from app.domain.auth.service import AuthService
from app.domain.profile.service import ProfileService
from app.models.profile import ProfileExperience


async def _user_id(db_session, email="svc@example.com") -> uuid.UUID:
    reg = await AuthService(db_session).register(email, "correct-passphrase", "S",
                                                 ip=None, user_agent=None)
    return reg.user.id


async def test_get_or_create_is_idempotent(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session)
    a = await svc.get_or_create(uid)
    b = await svc.get_or_create(uid)
    assert a.id == b.id


async def test_update_scalars_recomputes_strength(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "sc@example.com")
    p = await svc.update_scalars(uid, {"location": "Hyderabad",
                                       "career_goals": "Ship models."})
    assert p.location == "Hyderabad"
    assert p.profile_strength == 18  # location 8 + goals 10
    assert p.completeness["location"] is True


async def test_update_scalars_ignores_unknown_and_derived_keys(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "wl@example.com")
    p = await svc.update_scalars(uid, {"profile_strength": 999, "nope": 1,
                                       "location": "Berlin"})
    assert p.profile_strength == 8
    assert not hasattr(p, "nope")


async def test_add_update_delete_item_updates_counts(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "it@example.com")
    e = await svc.add_item(uid, "experiences", {"company": "Acme", "title": "Eng"})
    assert isinstance(e, ProfileExperience) and e.order_index == 0
    p = await svc.get_or_create(uid)
    assert p.profile_strength == 20
    await svc.update_item(uid, "experiences", e.id, {"title": "Senior Eng"})
    await svc.delete_item(uid, "experiences", e.id)
    p = await svc.get_or_create(uid)
    assert p.profile_strength == 0


async def test_item_ops_are_user_scoped(db_session):
    svc = ProfileService(db_session)
    mine = await _user_id(db_session, "mine@example.com")
    other = await _user_id(db_session, "other@example.com")
    e = await svc.add_item(other, "projects", {"name": "Theirs"})
    with pytest.raises(NotFoundError):
        await svc.update_item(mine, "projects", e.id, {"name": "Hacked"})
    with pytest.raises(NotFoundError):
        await svc.delete_item(mine, "projects", e.id)


async def test_reorder_reassigns_order_index(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "ord@example.com")
    a = await svc.add_item(uid, "education", {"institution": "A"})
    b = await svc.add_item(uid, "education", {"institution": "B"})
    out = await svc.reorder(uid, "education", [b.id, a.id])
    assert [r.institution for r in out] == ["B", "A"]
    assert [r.order_index for r in out] == [0, 1]


async def test_reorder_rejects_mismatched_id_set(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "bad@example.com")
    a = await svc.add_item(uid, "education", {"institution": "A"})
    with pytest.raises(ValidationAppError):
        await svc.reorder(uid, "education", [a.id, uuid.uuid4()])
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement**

`backend/app/domain/profile/service.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import current_request_id
from app.domain.profile.strength import ProfileCounts, compute_strength
from app.models.profile import (
    CareerProfile,
    ProfileCertification,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
)

SUBENTITY_MODELS: dict[str, type] = {
    "experiences": ProfileExperience,
    "education": ProfileEducation,
    "projects": ProfileProject,
    "certifications": ProfileCertification,
}
_SINGULAR = {
    "experiences": "experience", "education": "education",
    "projects": "project", "certifications": "certification",
}
_SCALAR_COLS = frozenset({
    "location", "github_url", "linkedin_url", "portfolio_url",
    "preferred_roles", "preferred_locations", "work_modes",
    "expected_salary_min", "expected_salary_max", "salary_currency",
    "salary_period", "years_experience", "seniority", "career_goals",
})


def _model(section: str) -> type:
    try:
        return SUBENTITY_MODELS[section]
    except KeyError:
        raise NotFoundError(detail=f"Unknown profile section '{section}'.") from None


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, user_id: uuid.UUID) -> CareerProfile:
        profile = (
            await self.session.execute(
                select(CareerProfile).where(CareerProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if profile is None:
            profile = CareerProfile(user_id=user_id)
            self.session.add(profile)
            await self.session.flush()
            await self._recompute(profile)
        return profile

    async def _count(self, profile_id: uuid.UUID, model: type) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count()).select_from(model).where(
                        model.profile_id == profile_id  # type: ignore[attr-defined]
                    )
                )
            ).scalar_one()
        )

    async def _recompute(self, profile: CareerProfile) -> None:
        counts = ProfileCounts(
            experiences=await self._count(profile.id, ProfileExperience),
            education=await self._count(profile.id, ProfileEducation),
            projects=await self._count(profile.id, ProfileProject),
            certifications=await self._count(profile.id, ProfileCertification),
        )
        result = compute_strength(profile, counts)
        profile.profile_strength = result.score
        profile.completeness = result.completeness
        await self.session.flush()

    async def _audit(self, action: str, user_id: uuid.UUID, meta: dict | None = None) -> None:
        await audit(
            self.session, actor_type="user", action=action, actor_user_id=user_id,
            resource_type="career_profile", request_id=current_request_id(), meta=meta,
        )

    async def load_full(
        self, user_id: uuid.UUID
    ) -> tuple[CareerProfile, dict[str, list[Any]]]:
        profile = await self.get_or_create(user_id)
        sections = {
            name: await self.list_section(user_id, name) for name in SUBENTITY_MODELS
        }
        return profile, sections

    async def update_scalars(self, user_id: uuid.UUID, patch: dict[str, Any]) -> CareerProfile:
        profile = await self.get_or_create(user_id)
        for key, value in patch.items():
            if key in _SCALAR_COLS:
                setattr(profile, key, value)
        await self.session.flush()
        await self._recompute(profile)
        await self._audit("profile.update", user_id, {"fields": sorted(
            k for k in patch if k in _SCALAR_COLS)})
        return profile

    async def list_section(self, user_id: uuid.UUID, section: str) -> list[Any]:
        model = _model(section)
        rows = (
            await self.session.execute(
                select(model)
                .where(model.user_id == user_id)  # type: ignore[attr-defined]
                .order_by(model.order_index, model.id)  # type: ignore[attr-defined]
            )
        ).scalars().all()
        return list(rows)

    async def _owned_item(self, user_id: uuid.UUID, section: str, item_id: uuid.UUID) -> Any:
        model = _model(section)
        item = (
            await self.session.execute(
                select(model).where(
                    model.id == item_id,  # type: ignore[attr-defined]
                    model.user_id == user_id,  # type: ignore[attr-defined]
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise NotFoundError(detail=f"{_SINGULAR[section]} not found")
        return item

    async def add_item(
        self, user_id: uuid.UUID, section: str, data: dict[str, Any]
    ) -> Any:
        model = _model(section)
        profile = await self.get_or_create(user_id)
        order_index = await self._count(profile.id, model)
        item = model(user_id=user_id, profile_id=profile.id, order_index=order_index,
                     source="user", **data)
        self.session.add(item)
        await self.session.flush()
        await self._recompute(profile)
        await self._audit(f"profile.{_SINGULAR[section]}.create", user_id,
                          {"id": str(item.id)})
        return item

    async def update_item(
        self, user_id: uuid.UUID, section: str, item_id: uuid.UUID, patch: dict[str, Any]
    ) -> Any:
        item = await self._owned_item(user_id, section, item_id)
        for key, value in patch.items():
            setattr(item, key, value)
        await self.session.flush()
        await self._recompute(await self.get_or_create(user_id))
        await self._audit(f"profile.{_SINGULAR[section]}.update", user_id,
                          {"id": str(item_id)})
        return item

    async def delete_item(
        self, user_id: uuid.UUID, section: str, item_id: uuid.UUID
    ) -> None:
        item = await self._owned_item(user_id, section, item_id)
        await self.session.delete(item)
        await self.session.flush()
        await self._recompute(await self.get_or_create(user_id))
        await self._audit(f"profile.{_SINGULAR[section]}.delete", user_id,
                          {"id": str(item_id)})

    async def reorder(
        self, user_id: uuid.UUID, section: str, ordered_ids: list[uuid.UUID]
    ) -> list[Any]:
        current = await self.list_section(user_id, section)
        if {r.id for r in current} != set(ordered_ids) or len(ordered_ids) != len(current):
            raise ValidationAppError(
                detail="The id list must be a permutation of this section's items."
            )
        by_id = {r.id: r for r in current}
        for position, item_id in enumerate(ordered_ids):
            by_id[item_id].order_index = position
        await self.session.flush()
        await self._recompute(await self.get_or_create(user_id))
        return [by_id[i] for i in ordered_ids]
```

- [ ] **Step 4: Run — expect pass** (DB-backed; run once Postgres is up + `ruff`/`mypy`/`lint-imports`).

Run: `cd backend && uv run pytest tests/domain/profile/test_service.py -q && uv run ruff check . && uv run lint-imports && uv run mypy app`

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/profile/service.py backend/tests/domain/profile/test_service.py
git commit -m "feat(profile): ProfileService — get-or-create, scalar update, sub-entity CRUD + reorder, strength recompute"
```

---

## Task 4: Profile schemas (`app/api/v1/schemas/profile.py`)

**Files:**
- Create: `backend/app/api/v1/schemas/profile.py`
- Test: `backend/tests/api/test_profile_schemas.py`

**Interfaces — Produces (`app.api.v1.schemas.profile`):**
- `HttpUrlStr` helper — a `field_validator` that accepts `None`/empty or a string starting `http://` / `https://` (≤ 300 chars), else `ValueError`.
- `CareerProfileUpdate` — every scalar/array column, all `Optional` with sensible constraints: `work_modes: list[Literal["remote","hybrid","onsite"]] | None`, `salary_period: Literal["year","month"] | None`, `seniority: Literal["junior","mid","senior","staff","lead","principal"] | None`, `expected_salary_min/max: int | None` (`ge=0`), `years_experience: float | None` (`ge=0, le=70`), url fields via `HttpUrlStr`. `model_config = ConfigDict(extra="forbid")`.
- `CareerProfileOut` — all columns + `profile_strength` + `completeness`, `from_attributes=True`.
- `StrengthOut` — `score: int`, `completeness: dict[str, bool]`, `missing: list[str]`.
- Per section: `ExperienceIn/Out`, `EducationIn/Out`, `ProjectIn/Out`, `CertificationIn/Out` (`*In` = `extra="forbid"`, required fields per the model's NOT NULLs, dates as `datetime.date`, `is_current: bool = False`; `*Out` = `from_attributes=True` incl. `id`, `order_index`, `source`).
- `SUBENTITY_SCHEMAS: dict[str, tuple[type[BaseModel], type[BaseModel]]]` — `{"experiences": (ExperienceIn, ExperienceOut), ...}` (create-schema, read-schema; `PATCH` uses `create.model_construct`-style partial — see Task 6).
- `ReorderIn` — `ids: list[uuid.UUID]` (`min_length=1`).
- `ProfileFullOut` — `CareerProfileOut` + `experiences/education/projects/certifications: list[...Out]`.

- [ ] **Step 1: Write the failing test**

`backend/tests/api/test_profile_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from app.api.v1.schemas.profile import (
    CareerProfileUpdate,
    ExperienceIn,
    ReorderIn,
)


def test_update_rejects_unknown_field():
    with pytest.raises(ValidationError):
        CareerProfileUpdate(nickname="Neo")


def test_update_rejects_bad_work_mode():
    with pytest.raises(ValidationError):
        CareerProfileUpdate(work_modes=["telepathy"])


def test_update_rejects_non_http_url():
    with pytest.raises(ValidationError):
        CareerProfileUpdate(github_url="ftp://nope")


def test_update_accepts_partial_valid_payload():
    m = CareerProfileUpdate(location="Hyderabad", work_modes=["remote", "hybrid"],
                            years_experience=5.5, seniority="senior")
    dumped = m.model_dump(exclude_unset=True)
    assert set(dumped) == {"location", "work_modes", "years_experience", "seniority"}


def test_experience_in_requires_company_and_title():
    with pytest.raises(ValidationError):
        ExperienceIn(company="Acme")


def test_reorder_in_requires_nonempty():
    with pytest.raises(ValidationError):
        ReorderIn(ids=[])
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** `backend/app/api/v1/schemas/profile.py` per the interface above. Key points: reuse one `_http_url` module function in each url field's `field_validator`; `*In` models set `model_config = ConfigDict(extra="forbid")`; date fields typed `datetime.date | None`.

- [ ] **Step 4: Run — expect pass** (pure; local).

Run: `cd backend && uv run pytest tests/api/test_profile_schemas.py -q && uv run ruff check . && uv run mypy app`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/schemas/profile.py backend/tests/api/test_profile_schemas.py
git commit -m "feat(api): career-profile request/response schemas"
```

---

## Task 5: `/profile` core router — `GET` / `PUT` / `GET /strength`

**Files:**
- Create: `backend/app/api/v1/profile.py` (core routes only in this task; the factory lands in Task 6)
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/api/test_profile.py`

**Interfaces — Produces:**
- `router = APIRouter(prefix="/profile", tags=["profile"])`
- `GET /profile` → `ProfileFullOut` — `ProfileService(db).load_full(user.id)`; always 200 (auto-creates).
- `PUT /profile` → `CareerProfileOut` — body `CareerProfileUpdate`; `update_scalars(user.id, body.model_dump(exclude_unset=True))`.
- `GET /profile/strength` → `StrengthOut` — recompute-free read from the stored `completeness` + a re-derived `missing` (call `compute_strength` with fresh counts so `missing` is always current).
- All three depend on `CurrentUser`. Registered before the sub-entity routers in Task 6.

- [ ] **Step 1: Write the failing test**

`backend/tests/api/test_profile.py`:

```python
import pytest

BASE = "/api/v1/profile"


async def _auth(client, email="prof@example.com"):
    r = await client.post("/api/v1/auth/register",
                          json={"email": email, "password": "correct-passphrase",
                                "full_name": "Prof"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_get_profile_autocreates_and_returns_full_shape(client):
    h = await _auth(client)
    r = await client.get(BASE, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["profile_strength"] == 0
    assert body["experiences"] == [] and body["education"] == []


async def test_get_profile_requires_auth(client):
    assert (await client.get(BASE)).status_code == 401


async def test_put_profile_updates_and_rescores(client):
    h = await _auth(client, "put@example.com")
    r = await client.put(BASE, headers=h,
                         json={"location": "Hyderabad", "career_goals": "Ship models."})
    assert r.status_code == 200
    assert r.json()["profile_strength"] == 18
    assert r.json()["completeness"]["location"] is True


async def test_put_profile_rejects_unknown_field(client):
    h = await _auth(client, "unk@example.com")
    r = await client.put(BASE, headers=h, json={"nickname": "Neo"})
    assert r.status_code == 422


async def test_strength_endpoint_lists_missing(client):
    h = await _auth(client, "str@example.com")
    r = await client.get(f"{BASE}/strength", headers=h)
    assert r.status_code == 200
    assert r.json()["score"] == 0
    assert "Add your work experience" in r.json()["missing"]
```

- [ ] **Step 2: Run — expect fail** (404s / module missing).

- [ ] **Step 3: Implement** the three routes; wire `api_router.include_router(profile.router)` in `router.py` (after `auth`).

- [ ] **Step 4: Run — expect pass** (DB-backed; run with Postgres + `ruff`/`mypy`/`lint-imports`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/profile.py backend/app/api/v1/router.py backend/tests/api/test_profile.py
git commit -m "feat(api): /profile — get full profile, update scalars, strength"
```

---

## Task 6: Generic sub-entity router factory + wire four resources

**Files:**
- Modify: `backend/app/api/v1/profile.py` (add `_make_subentity_router` + include four)
- Test: `backend/tests/api/test_profile_subentities.py`

**Interfaces — Produces:**
- `_make_subentity_router(section: str) -> APIRouter` returning a router mounted at `/profile/{section}` with:
  - `GET ""` → `list[<Section>Out]` — `service.list_section`.
  - `POST ""` → `201 <Section>Out` — body `<Section>In`; `service.add_item`.
  - `PATCH "/{item_id}"` → `<Section>Out` — body = a partial model (`<Section>In` with all fields optional via `create_model`/`model_construct`; simplest: a second `<Section>Patch` model with every field `Optional` + `extra="forbid"`, defined in Task 4 schemas — **add these `*Patch` models to Task 4's schema file**); `service.update_item(..., patch.model_dump(exclude_unset=True))`.
  - `DELETE "/{item_id}"` → `204` — `service.delete_item`.
  - `POST "/reorder"` → `list[<Section>Out]` — body `ReorderIn`; `service.reorder`.
  - Every route depends on `CurrentUser`.
- `profile.py` includes `_make_subentity_router(s) for s in ("experiences", "education", "projects", "certifications")`.

> **Schema addition (fold into Task 4 if not yet done):** `ExperiencePatch`, `EducationPatch`, `ProjectPatch`, `CertificationPatch` — same fields as the `*In` models but every field `Optional` with no defaults, `model_config = ConfigDict(extra="forbid")`. Register in `SUBENTITY_SCHEMAS` as a third tuple element `(In, Out, Patch)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/api/test_profile_subentities.py`:

```python
import pytest

REG = "/api/v1/auth/register"


async def _auth(client, email):
    r = await client.post(REG, json={"email": email, "password": "correct-passphrase",
                                     "full_name": "X"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.parametrize(
    ("section", "create", "patch"),
    [
        ("experiences", {"company": "Acme", "title": "Eng"}, {"title": "Senior Eng"}),
        ("education", {"institution": "Uni"}, {"degree": "BSc"}),
        ("projects", {"name": "RAG"}, {"url": "https://x.dev"}),
        ("certifications", {"name": "AWS SAA"}, {"issuer": "AWS"}),
    ],
)
async def test_subentity_full_crud(client, section, create, patch):
    h = await _auth(client, f"{section}@example.com")
    base = f"/api/v1/profile/{section}"

    empty = await client.get(base, headers=h)
    assert empty.status_code == 200 and empty.json() == []

    created = await client.post(base, headers=h, json=create)
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert created.json()["order_index"] == 0 and created.json()["source"] == "user"

    patched = await client.patch(f"{base}/{item_id}", headers=h, json=patch)
    assert patched.status_code == 200
    key, val = next(iter(patch.items()))
    assert patched.json()[key] == val

    listed = await client.get(base, headers=h)
    assert len(listed.json()) == 1

    deleted = await client.delete(f"{base}/{item_id}", headers=h)
    assert deleted.status_code == 204
    assert (await client.get(base, headers=h)).json() == []


async def test_subentity_reorder(client):
    h = await _auth(client, "reorder@example.com")
    base = "/api/v1/profile/education"
    a = (await client.post(base, headers=h, json={"institution": "A"})).json()["id"]
    b = (await client.post(base, headers=h, json={"institution": "B"})).json()["id"]
    r = await client.post(f"{base}/reorder", headers=h, json={"ids": [b, a]})
    assert r.status_code == 200
    assert [row["institution"] for row in r.json()] == ["B", "A"]


async def test_subentity_patch_rejects_unknown_field(client):
    h = await _auth(client, "pu@example.com")
    base = "/api/v1/profile/projects"
    pid = (await client.post(base, headers=h, json={"name": "P"})).json()["id"]
    r = await client.patch(f"{base}/{pid}", headers=h, json={"bogus": 1})
    assert r.status_code == 422


async def test_subentity_cross_user_returns_404(client):
    h1 = await _auth(client, "u1@example.com")
    h2 = await _auth(client, "u2@example.com")
    base = "/api/v1/profile/projects"
    pid = (await client.post(base, headers=h1, json={"name": "Mine"})).json()["id"]
    assert (await client.patch(f"{base}/{pid}", headers=h2, json={"name": "x"})).status_code == 404
    assert (await client.delete(f"{base}/{pid}", headers=h2)).status_code == 404


async def test_creating_experience_bumps_strength(client):
    h = await _auth(client, "bump@example.com")
    await client.post("/api/v1/profile/experiences", headers=h,
                      json={"company": "Acme", "title": "Eng"})
    prof = await client.get("/api/v1/profile", headers=h)
    assert prof.json()["profile_strength"] == 20
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** `_make_subentity_router`. Use closures over `section`; pull `(In, Out, Patch)` from `SUBENTITY_SCHEMAS`. `response_model` per route from `Out`. Keep the factory < 60 lines.

- [ ] **Step 4: Run — expect pass** (DB-backed; Postgres + `ruff`/`mypy`/`lint-imports`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/profile.py backend/app/api/v1/schemas/profile.py backend/tests/api/test_profile_subentities.py
git commit -m "feat(api): generic /profile sub-entity CRUD + reorder for the four sections"
```

---

## Task 7: Phase 1b verification & report

- [ ] **Step 1: Full backend gate**

Run: `cd backend && uv run ruff check . && uv run lint-imports && uv run mypy app && uv run pytest -q`
Expected: ruff clean; import-linter 2 contracts kept; mypy clean; pytest all green (Phase 0 + 1a + 1b) once Postgres is available.

- [ ] **Step 2: OpenAPI sanity**

Run: `cd backend && uv run python -c "from app.main import create_app; print(sorted(p for p in create_app().openapi()['paths'] if '/profile' in p))"`
Expected: `/api/v1/profile`, `/api/v1/profile/strength`, and `.../{experiences,education,projects,certifications}` + `.../{section}/{item_id}` + `.../{section}/reorder`.

- [ ] **Step 3: Fill the completion report below** (what changed, files, test count, deviations).

- [ ] **Step 4: Commit** `docs: Phase 1b completion report`.

---

## Phase 1b completion report (fill in when done)

- **What changed:** _[list]_
- **Why:** the structured career profile + a live strength score is what the dashboard's "profile strength" and the Phase 5 matcher read from; the four sub-entity resources are the editable spine of the Résumé Workspace.
- **Files changed:** _[list]_
- **How to test:** `cd backend && uv run pytest tests/api/test_profile.py tests/api/test_profile_subentities.py -q`.
- **Regression check:** Phase 0 + 1a suites still green; `/auth/*` and `/health*` unchanged; `lint-imports` still 2 contracts kept; migration chain `0001→0002→0003→0004` linear.
- **Baseline:** _[N backend tests, M% coverage]_
- **Deviations:** _[list]_

---

## Self-Review

**1. Spec coverage (profile slice of §9 Phase 1 + §1.4 + §5.3 + §6.2):**
- `career_profiles` (1:1 user) + four sub-entity tables → Task 1. ✓
- `GET /profile` · `PUT /profile` · `GET /profile/strength` → Task 5. ✓
- `/experiences` `/education` `/projects` `/certifications` each `GET`/`POST`/`PATCH {id}`/`DELETE {id}`/`POST /reorder` → Task 6. ✓
- Deterministic strength score (`§1.4` — "not an LLM") → Task 2 (pure `compute_strength`), recomputed on every mutation in Task 3. ✓
- Per-user isolation → every query filters `user_id`; cross-user item ops → `NotFoundError` (Task 3 + Task 6 tests). ✓
- Audit on every mutation → `ProfileService._audit` (`profile.update`, `profile.<section>.<op>`). ✓
- **Deferred (Phase 3, flagged in the header):** `skills` taxonomy, `profile_skills`, `/profile/skills`, `GET /api/v1/skills`, résumé-`source` rows.

**2. Placeholder scan:** Tasks 1–3 and 5–6 carry literal code or a precise interface contract; Task 4's schema file is described field-by-field rather than fully transcribed (mechanical Pydantic) — the tests pin its behavior. No "TBD".

**3. Type consistency:**
- `ProfileService(session)` — Task 3; consumed by Tasks 5–6 as `ProfileService(db)`.
- `compute_strength(profile, ProfileCounts(...)) -> StrengthResult(score, completeness, missing)` — Task 2; called in `ProfileService._recompute` and the `/strength` route.
- `SUBENTITY_MODELS` (service) and `SUBENTITY_SCHEMAS` (schemas) share the exact keys `experiences|education|projects|certifications`; `_SINGULAR` maps them for audit actions and 404 detail.
- `CareerProfileUpdate.model_dump(exclude_unset=True)` → `ProfileService.update_scalars` whitelists against `_SCALAR_COLS` (defence in depth even though the schema `forbid`s extras).
- Migration chain: `0003_users` → `0004_career_profiles`. ✓
- `_SubEntity` is an unmapped mixin; concrete classes are `(_SubEntity, Base)` so `TimestampMixin.created_at/updated_at` + the mixin columns land on each table. Verified by `test_subentity_round_trip_and_cascade`.

**4. Ambiguity check:** `reorder` requires an exact permutation of the section's current ids (not a subset) — `ValidationAppError` otherwise; pinned by `test_reorder_rejects_mismatched_id_set`. `PUT /profile` is a partial update (only `exclude_unset` keys), not a full replace — pinned by `test_update_accepts_partial_valid_payload` + `test_put_profile_updates_and_rescores`.

---

## Execution Handoff

Phase 1a's branch is `phase-1a-auth`. Options for 1b:
1. **Continue on `phase-1a-auth`** (1b builds directly on 1a's `get_current_user` + `User` model) — simplest; Phase 1 ships as one unit.
2. **New branch `phase-1b-career-profile`** off `phase-1a-auth`.

Then: **Subagent-Driven** (fresh subagent per task, review between) or **Inline** (`superpowers:executing-plans`). Note: Tasks 1, 3, 5, 6 are DB-backed — they need Postgres 16 + pgvector + Redis 7 (Docker Compose `db` + `redis`, or CI) to run their tests; Tasks 2 and 4 run fully offline.
