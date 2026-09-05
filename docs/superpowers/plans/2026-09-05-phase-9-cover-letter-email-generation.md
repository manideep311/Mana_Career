# Phase 9 — Cover letter + email generation (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two new bounded agent nodes — `cover_letter` and `email_draft` — that turn a tailored résumé into a grounded cover letter and a drafted application email, behind a `prepare_application` goal (its literal already exists, unused, from Phase 7a). Plus a `generation` eval suite added to `/eval`.

**Architecture:** Generalize `ClaimValidator` to take plain claim lines instead of a `ResumeExtraction` (so it's reusable for cover letters). Two new `generation/` primitives (`write_cover_letter`, `draft_email`) mirroring `tailor_resume`'s shape. Two new tables (`cover_letters`, `application_emails`, migration `0012`). Three new graph nodes (`cover_letter`, `letter_claim_validator`, `email_draft`) extending the existing `resume_tailoring → claim_validator` chain behind the `prepare_application` goal. A `generation` eval suite mirroring the existing `retrieval` suite's shape.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, LangGraph, ARQ + Redis, pydantic-settings, pgvector.

**Spec:** `docs/superpowers/specs/2026-09-05-phase-9-cover-letter-email-generation.md` (read this first — it has 8 rulings, R1-R8, that resolve every ambiguity in this plan) + master `2026-08-30-mana-career-design.md` §4.2/§4.3/§5.3/§9.

## Global Constraints

- **No frontend, no new API endpoint this phase** (spec R7). Everything is verified via pure unit tests + one DB-gated worker-integration test, exactly like `tests/worker/test_tailoring_task.py`.
- `LLM_PROVIDER=fake` / `EMBEDDINGS_PROVIDER=fake` in CI and every test. `FakeLLMProvider().complete(schema=X)` (no `scripted` list) stubs every field to its type's zero-value — an empty string for `str`. Tests assert plumbing, never LLM output quality.
- **No local Postgres/Redis.** DB-backed tests ERROR at `tests/conftest.py`'s `_migrated` fixture and run only in CI. Local gates: `"$UV" run ruff check .` / `"$UV" run lint-imports` / `"$UV" run mypy app` / `"$UV" run pytest -q --collect-only` (error-free) + the pure test suites named per task. `$UV` = `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`. Do NOT run a full DB test file locally.
- Alembic chain `…→0011_resume_tailoring→0012_application_documents`, single head. Mirror `0011_resume_tailoring.py`'s style exactly (it is the freshest, most-reviewed precedent) — no `Computed`/vector columns needed this time (no chunking phase for cover letters/emails).
- `app.domain.generation.cover_letter` importing `ClaimValidator`/`_split_sentences` from `app.domain.resume.tailoring` is allowed by the import-linter contracts (same shape as `documents → resume` for `ResumeExtraction`, already approved in Phase 8a). **No new import-linter contract** — stays `Contracts: 3 kept, 0 broken`.
- `mypy` is `strict = true`. Every def fully annotated.
- Node budget bumps are INLINE (`state["budget"]["llm_calls_made"] += N; state["budget"]["cost_usd"] += cost`) — no helper (Phase-7a ruling, still in force).
- All tuning values (prompt versions, token caps, eval floors) are module-level named constants.
- `ManaState` already has `cover_letter_id`, `email_draft_id`, `application_id` keys (Phase 7a, unused until now) and `AgentGoal` already includes `"prepare_application"` (unused until now) — **no changes needed to those two things**. Only `NODE_ORDER` (documentation-only, not consumed by `graph.py`'s actual wiring — verified) needs extending.

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `backend/app/domain/resume/tailoring.py` | Modify | `ClaimValidator.check()` takes `claim_lines: list[str]`; new `_resume_claim_lines()` |
| `backend/app/domain/agents/nodes/claim_validator.py` | Modify | one call-site update for the new `ClaimValidator.check()` signature |
| `backend/app/domain/generation/cover_letter.py` | Create | `CoverLetterDraft`, `write_cover_letter()`, local `_collect_sources`/`_render_prompt` |
| `backend/app/domain/generation/email_draft.py` | Create | `EmailDraft`, `draft_email()` |
| `backend/app/models/application.py` | Create | `CoverLetter`, `ApplicationEmail` |
| `backend/app/models/__init__.py` | Modify | `from app.models import application as application` after `ai` |
| `backend/alembic/versions/0012_application_documents.py` | Create | `cover_letters`, `application_emails` tables + triggers |
| `backend/app/domain/agents/blocks.py` | Modify | `ApplicationDraftBlock` gains 3 optional id fields, `application_id` becomes optional |
| `backend/app/domain/agents/state.py` | Modify | `NODE_ORDER` gains 3 entries |
| `backend/app/domain/agents/nodes/cover_letter.py` | Create | the `cover_letter` node |
| `backend/app/domain/agents/nodes/letter_claim_validator.py` | Create | the letter re-check node |
| `backend/app/domain/agents/nodes/email_draft.py` | Create | the `email_draft` node |
| `backend/app/domain/agents/nodes/supervisor.py` | Modify | route `prepare_application` → `resume_tailoring` |
| `backend/app/domain/agents/nodes/respond.py` | Modify | new first branch on `state["email_draft_id"]` |
| `backend/app/domain/agents/nodes/__init__.py` | Modify | re-export the 3 new nodes |
| `backend/app/domain/agents/graph.py` | Modify | add 3 nodes, goal-aware branch after `claim_validator`, new edges |
| `backend/eval/datasets/generation/golden_v1.jsonl` | Create | 4 generation eval cases |
| `backend/eval/suites/generation.py` | Create | `run_generation_suite()` |
| `backend/eval/thresholds.py` | Modify | 4 new floor constants |
| `backend/eval/run.py` | Modify | `choices=["retrieval","generation"]` + dispatch |
| `backend/app/api/v1/schemas/eval.py` | Modify | `EvalRunIn.suite` widens |
| `backend/app/api/v1/eval.py` | Modify | dispatch on `body.suite` |
| `.github/workflows/ci.yml` | Modify | + generation eval CI step |
| tests | Create | `tests/domain/generation/test_cover_letter.py` · `test_email_draft.py` · `tests/models/test_application_models.py` (DB) · `tests/domain/agents/test_nodes_application.py` · `tests/domain/agents/test_graph_prepare_application.py` · `tests/worker/test_prepare_application_task.py` (DB) · `tests/eval/test_generation_suite.py` (DB) |
| tests | Modify | `tests/domain/resume/test_tailoring.py` (3 call-sites) |

---

## Task 1: generalize `ClaimValidator`

**Files:** Modify `backend/app/domain/resume/tailoring.py`, `backend/app/domain/agents/nodes/claim_validator.py`, `backend/tests/domain/resume/test_tailoring.py`.

**Interfaces:**
- Produces: `_resume_claim_lines(tailored: ResumeExtraction) -> list[str]`; `ClaimValidator.check(self, claim_lines: list[str]) -> ClaimReport` (was `check(self, tailored: ResumeExtraction)`).
- Consumes: nothing new.

- [ ] **Step 1: `tailoring.py`** — replace the `ClaimValidator.check` method and add the extraction function. The current method body (lines building `claim_lines` from `tailored.experiences`/`.projects`/`.summary`) becomes a standalone function; `check` takes the already-built list:

```python
def _resume_claim_lines(tailored: ResumeExtraction) -> list[str]:
    claim_lines: list[str] = []
    for exp in tailored.experiences:
        claim_lines.extend(exp.highlights)
        if exp.description and exp.description.strip():
            claim_lines.extend(_split_sentences(exp.description))
    for proj in tailored.projects:
        claim_lines.extend(proj.highlights)
        if proj.description and proj.description.strip():
            claim_lines.extend(_split_sentences(proj.description))
    if tailored.summary and tailored.summary.strip():
        claim_lines.extend(_split_sentences(tailored.summary))
    return claim_lines


class ClaimValidator:
    def __init__(self, sources: list[str]) -> None:
        self._source_tokens = [self._norm(s) for s in sources if s.strip()]

    @staticmethod
    def _norm(s: str) -> frozenset[str]:
        lowered = s.lower()
        stripped = _PUNCT_RE.sub(" ", lowered)
        tokens = stripped.split()
        return frozenset(t for t in tokens if t not in _STOPWORDS)

    def _supported(self, claim: str) -> bool:
        ct = self._norm(claim)
        if not ct:
            return True
        best = max(
            (len(ct & st) / len(ct) for st in self._source_tokens), default=0.0
        )
        return best >= _MIN_SUPPORT

    def check(self, claim_lines: list[str]) -> ClaimReport:
        checked = 0
        unsupported: list[str] = []
        for line in claim_lines:
            if not line.strip():
                continue
            checked += 1
            if not self._supported(line):
                unsupported.append(line)

        supported_ratio = (
            (checked - len(unsupported)) / checked if checked else 1.0
        )
        return ClaimReport(
            checked=checked,
            unsupported=unsupported,
            supported_ratio=supported_ratio,
            passed=not unsupported,
        )
```

(`ClaimReport`, `_split_sentences`, `_STOPWORDS`, `_MIN_SUPPORT`, `_PUNCT_RE`, `_collect_sources`, `_render_prompt`, `tailor_resume`, `MAX_CLAIM_REPROMPTS`, `_TAILOR_SYSTEM`, `_TAILOR_PROMPT_VERSION` are all unchanged — only the `check` method's body moves out and its signature changes.)

- [ ] **Step 2: `tailor_resume()`'s one call site** — change:
```python
        report = validator.check(tailored)
```
to:
```python
        report = validator.check(_resume_claim_lines(tailored))
```

- [ ] **Step 3: `nodes/claim_validator.py`'s one call site** — change the import and the call:
```python
from app.domain.resume.tailoring import ClaimValidator, _collect_sources, _resume_claim_lines
```
and:
```python
    report = ClaimValidator(sources).check(_resume_claim_lines(tailored))
```
(was `.check(tailored)`).

- [ ] **Step 4: `tests/domain/resume/test_tailoring.py`** — add `_resume_claim_lines` to the import, and update the 3 direct `.check(...)` calls:
```python
from app.domain.resume.tailoring import (
    ClaimValidator,
    _collect_sources,
    _resume_claim_lines,
    tailor_resume,
)
```
`test_validator_passes_when_highlights_are_grounded`: `report = v.check(_resume_claim_lines(b))`.
`test_validator_flags_an_invented_highlight`: `report = v.check(_resume_claim_lines(tailored))`.
`test_validator_ignores_blank_and_structural_lines`: `report = v.check(_resume_claim_lines(tailored))`.
(`test_tailor_resume_loop_shape_with_fake_llm` is unchanged — it never calls `.check()` directly.)

- [ ] **Step 5: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/resume/test_tailoring.py`
Expected: all PASS (7 tests: 3 validator + 1 loop-shape + whatever else is already in that file — re-check the file's own full test count before asserting an exact number).

```bash
git add backend/app/domain/resume/tailoring.py backend/app/domain/agents/nodes/claim_validator.py backend/tests/domain/resume/test_tailoring.py
git commit -m "refactor(resume): ClaimValidator.check() takes claim lines, not a ResumeExtraction"
```

---

## Task 2: `write_cover_letter` generation primitive

**Files:** Create `backend/app/domain/generation/cover_letter.py`, `backend/tests/domain/generation/test_cover_letter.py`.

**Interfaces:**
- Consumes: `GenerationService` (`app.domain.generation.service`), `GenerationMeta` (`app.domain.generation.types`), `ResumeExtraction` (`app.domain.resume.extractor`), `ClaimValidator`/`_split_sentences`/`MAX_CLAIM_REPROMPTS` (`app.domain.resume.tailoring`, per Task 1's new signature).
- Produces: `CoverLetterDraft(content: str)`; `write_cover_letter(*, gen, base, profile_summary, job_brief, tone="professional") -> tuple[CoverLetterDraft, GenerationMeta]`, used by Task 5's `cover_letter` node.

- [ ] **Step 1: `app/domain/generation/cover_letter.py`**

```python
from __future__ import annotations

import json
from dataclasses import replace

from pydantic import BaseModel

from app.domain.generation.service import GenerationService
from app.domain.generation.types import GenerationMeta
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.tailoring import MAX_CLAIM_REPROMPTS, ClaimValidator, _split_sentences

_LETTER_SYSTEM = (
    "You write a concise, professional cover letter for a job application. "
    "You may reference the candidate's experience, skills, and projects from "
    "the provided résumé and profile, and may reference the job posting. You "
    "must NOT invent employers, titles, dates, metrics, technologies, or "
    "accomplishments that are not already present in the provided résumé and "
    "profile. Return the full letter body as plain text, 3-5 short paragraphs "
    "separated by blank lines. Do not include a salutation placeholder like "
    "'[Hiring Manager]' -- address it generically ('Dear Hiring Team,')."
)
_LETTER_PROMPT_VERSION = "cover-letter-1"


class CoverLetterDraft(BaseModel):
    content: str


def _collect_sources(base: ResumeExtraction, profile_summary: str, job_brief: str) -> list[str]:
    """Sources a cover letter's claims may draw on.

    Deliberately NOT shared with ``resume.tailoring._collect_sources``: a
    cover letter may also reference the job posting itself ("your team's
    focus on X excites me"), which is not a valid grounding source when
    tailoring a résumé (the job is what you're tailoring *toward*, not a
    claim about the candidate).
    """
    sources: list[str] = []

    def _add(*values: str | None) -> None:
        for v in values:
            if v and v.strip():
                sources.append(v)

    _add(base.summary)
    for exp in base.experiences:
        _add(exp.description, exp.title, exp.company)
        sources.extend(h for h in exp.highlights if h and h.strip())
        sources.extend(t for t in exp.tech if t and t.strip())
    for proj in base.projects:
        _add(proj.description, proj.name)
        sources.extend(h for h in proj.highlights if h and h.strip())
        sources.extend(t for t in proj.tech if t and t.strip())
    for edu in base.education:
        _add(edu.institution, edu.degree, edu.field)
    for cert in base.certifications:
        _add(cert.name, cert.issuer)
    sources.extend(s for s in base.skills if s and s.strip())
    if profile_summary and profile_summary.strip():
        sources.extend(_split_sentences(profile_summary))
    if job_brief and job_brief.strip():
        sources.extend(_split_sentences(job_brief))
    return sources


def _render_prompt(
    base: ResumeExtraction,
    profile_summary: str,
    job_brief: str,
    tone: str,
    rejected: list[str] | None,
) -> str:
    base_json = json.dumps(base.model_dump(mode="json"), indent=2)
    parts = [
        f"Base résumé (JSON):\n{base_json}",
        f"Candidate profile summary:\n{profile_summary}",
        f"Target job:\n{job_brief}",
        f"Tone: {tone}",
    ]
    if rejected:
        rejected_lines = "\n".join(f"- {line}" for line in rejected)
        parts.append(
            "The following lines were not grounded in the source material; "
            f"rewrite or drop them:\n{rejected_lines}"
        )
    return "\n\n".join(parts)


async def write_cover_letter(
    *,
    gen: GenerationService,
    base: ResumeExtraction,
    profile_summary: str,
    job_brief: str,
    tone: str = "professional",
) -> tuple[CoverLetterDraft, GenerationMeta]:
    sources = _collect_sources(base, profile_summary, job_brief)
    validator = ClaimValidator(sources)
    user = _render_prompt(base, profile_summary, job_brief, tone, rejected=None)
    for attempt in range(MAX_CLAIM_REPROMPTS + 1):
        res = await gen.generate(
            system=_LETTER_SYSTEM,
            user=user,
            schema=CoverLetterDraft,
            prompt_version=_LETTER_PROMPT_VERSION,
            max_tokens=900,
        )
        draft = CoverLetterDraft.model_validate(res.structured)
        report = validator.check(_split_sentences(draft.content))
        meta = replace(res.meta, claim_validation=report.as_dict())
        if report.passed or attempt == MAX_CLAIM_REPROMPTS:
            return draft, meta
        user = _render_prompt(base, profile_summary, job_brief, tone, rejected=report.unsupported)
    raise AssertionError("unreachable")
```

- [ ] **Step 2: `tests/domain/generation/test_cover_letter.py`**

```python
from app.domain.generation.cover_letter import (
    CoverLetterDraft,
    _collect_sources,
    write_cover_letter,
)
from app.domain.generation.service import GenerationService
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.resume.extractor import ExtractedExperience, ResumeExtraction
from app.domain.resume.tailoring import ClaimValidator


def _base() -> ResumeExtraction:
    return ResumeExtraction(
        full_name="A. Dev",
        summary="Backend engineer focused on Python services and Postgres.",
        skills=["python", "postgresql"],
        experiences=[
            ExtractedExperience(
                company="Acme", title="Senior Engineer",
                description="Owned the billing service.",
                highlights=["Cut p99 latency on the billing API by 40 percent"],
            )
        ],
    )


def test_collect_sources_includes_job_brief():
    b = _base()
    sources = _collect_sources(b, "", "We build resilient payments infrastructure.")
    assert any("resilient payments" in s for s in sources)


def test_validator_flags_an_invented_claim_in_a_letter():
    b = _base()
    sources = _collect_sources(b, "", "")
    v = ClaimValidator(sources)
    report = v.check(["I previously led a team of 200 engineers."])
    assert report.passed is False


async def test_write_cover_letter_loop_shape_with_fake_llm():
    b = _base()
    gen = GenerationService(FakeLLMProvider())
    draft, meta = await write_cover_letter(
        gen=gen, base=b, profile_summary="", job_brief="Senior Python role at Globex"
    )
    # FakeLLMProvider stubs the schema to empty -> an empty letter, 0 claims, passes.
    assert isinstance(draft, CoverLetterDraft)
    assert draft.content == ""
    assert meta.claim_validation["checked"] == 0
    assert meta.claim_validation["passed"] is True
    assert meta.prompt_version == "cover-letter-1"
```

- [ ] **Step 3: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/generation/test_cover_letter.py`
Expected: all PASS (3 tests).

```bash
git add backend/app/domain/generation/cover_letter.py backend/tests/domain/generation/test_cover_letter.py
git commit -m "feat(gen): write_cover_letter primitive -- reprompt loop + claim validation"
```

---

## Task 3: `draft_email` generation primitive

**Files:** Create `backend/app/domain/generation/email_draft.py`, `backend/tests/domain/generation/test_email_draft.py`.

**Interfaces:**
- Consumes: `GenerationService`, `GenerationMeta`.
- Produces: `EmailDraft(subject: str, body: str)`; `draft_email(*, gen, job_title, company, applicant_name, cover_letter_content) -> tuple[EmailDraft, GenerationMeta]`, used by Task 5's `email_draft` node.

- [ ] **Step 1: `app/domain/generation/email_draft.py`**

```python
from __future__ import annotations

from pydantic import BaseModel

from app.domain.generation.service import GenerationService
from app.domain.generation.types import GenerationMeta

_EMAIL_SYSTEM = (
    "You write a short, professional application email that accompanies a "
    "cover letter. Keep it to 3-5 sentences: state the role being applied "
    "for, mention that the résumé and cover letter are attached, and close "
    "politely. Do not repeat the full cover letter verbatim. Return a "
    "subject line and the email body as plain text."
)
_EMAIL_PROMPT_VERSION = "email-draft-1"


class EmailDraft(BaseModel):
    subject: str
    body: str


async def draft_email(
    *,
    gen: GenerationService,
    job_title: str,
    company: str,
    applicant_name: str,
    cover_letter_content: str,
) -> tuple[EmailDraft, GenerationMeta]:
    user = (
        f"Job title: {job_title}\n"
        f"Company: {company}\n"
        f"Applicant name: {applicant_name}\n\n"
        f"Cover letter (for reference, do not repeat verbatim):\n{cover_letter_content}"
    )
    res = await gen.generate(
        system=_EMAIL_SYSTEM,
        user=user,
        schema=EmailDraft,
        prompt_version=_EMAIL_PROMPT_VERSION,
        max_tokens=400,
    )
    draft = EmailDraft.model_validate(res.structured)
    return draft, res.meta
```

- [ ] **Step 2: `tests/domain/generation/test_email_draft.py`**

```python
from app.domain.generation.email_draft import EmailDraft, draft_email
from app.domain.generation.service import GenerationService
from app.domain.llm.adapters.fake import FakeLLMProvider


async def test_draft_email_shape_with_fake_llm():
    gen = GenerationService(FakeLLMProvider())
    draft, meta = await draft_email(
        gen=gen,
        job_title="Senior Backend Engineer",
        company="Globex",
        applicant_name="A. Dev",
        cover_letter_content="Dear Hiring Team,\n\nI am excited to apply.\n\nSincerely,\nA. Dev",
    )
    assert isinstance(draft, EmailDraft)
    assert draft.subject == ""  # FakeLLMProvider stubs str fields to ""
    assert meta.prompt_version == "email-draft-1"
```

- [ ] **Step 3: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/generation/test_email_draft.py`
Expected: all PASS (1 test).

```bash
git add backend/app/domain/generation/email_draft.py backend/tests/domain/generation/test_email_draft.py
git commit -m "feat(gen): draft_email primitive -- single schema-constrained LLM call"
```

---

## Task 4: migration `0012` + `CoverLetter`/`ApplicationEmail` models

**Files:** Create `backend/app/models/application.py`, `backend/alembic/versions/0012_application_documents.py`, `backend/tests/models/test_application_models.py`. Modify `backend/app/models/__init__.py`.

**Interfaces:**
- Produces: `CoverLetter` (table `cover_letters`), `ApplicationEmail` (table `application_emails`); single alembic head `0012_application_documents`.

- [ ] **Step 1: `app/models/application.py`**

```python
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CoverLetter(Base, TimestampMixin):
    __tablename__ = "cover_letters"
    __table_args__ = (
        CheckConstraint(
            "created_by in ('user','mana_ai')", name="cover_letters_created_by_valid"
        ),
        Index("ix_cover_letters_user", "user_id", text("created_at DESC")),
        Index("ix_cover_letters_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK on job_id/application_id/resume_version_id/supersedes_id: loose optional
    # cross-references, mirroring the resume_versions precedent (migration 0011).
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tone: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'professional'")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    rendered_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    generation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'mana_ai'")
    )


class ApplicationEmail(Base, TimestampMixin):
    __tablename__ = "application_emails"
    __table_args__ = (
        CheckConstraint(
            "body_format in ('plain','html')", name="application_emails_body_format_valid"
        ),
        CheckConstraint(
            "status in ('draft','awaiting_approval','approved','sending','sent','failed','canceled')",
            name="application_emails_status_valid",
        ),
        Index("ix_application_emails_user", "user_id", text("created_at DESC")),
        Index("ix_application_emails_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # to_email/to_name/provider nullable: a draft has no recipient/provider yet
    # (Phase 9 has no recipient-inference or send capability -- Phase 10's
    # review step is where a human fills these in before approval).
    to_email: Mapped[str | None] = mapped_column(String(320))
    to_name: Mapped[str | None] = mapped_column(String(200))
    cc: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    bcc: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_format: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'plain'")
    )
    attachment_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'draft'")
    )
    provider: Mapped[str | None] = mapped_column(String(16))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    send_error: Mapped[str | None] = mapped_column(Text)
    generation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
```

- [ ] **Step 2: `app/models/__init__.py`** — insert alphabetically after `ai`:
```python
from app.models import ai as ai
from app.models import application as application
from app.models import audit as audit
```
(and add `"application"`... no — this file has no `__all__` entries per module, only `["Base"]`; just insert the import line, nothing else changes.)

- [ ] **Step 3: `alembic/versions/0012_application_documents.py`**

```python
"""cover_letters + application_emails tables

Revision ID: 0012_application_documents
Revises: 0011_resume_tailoring
Create Date: 2026-09-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0012_application_documents"
down_revision = "0011_resume_tailoring"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "cover_letters",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", pg.UUID(as_uuid=True)),
        sa.Column("resume_version_id", pg.UUID(as_uuid=True)),
        sa.Column("tone", sa.String(24), nullable=False,
                  server_default=sa.text("'professional'")),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_json", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("rendered_refs", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("generation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("supersedes_id", pg.UUID(as_uuid=True)),
        sa.Column("created_by", sa.String(16), nullable=False,
                  server_default=sa.text("'mana_ai'")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "created_by in ('user','mana_ai')",
            name="cover_letters_created_by_valid",
        ),
    )
    op.create_index("ix_cover_letters_user", "cover_letters",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_cover_letters_job", "cover_letters", ["job_id"])
    op.execute("CREATE TRIGGER trg_cover_letters_set_updated_at BEFORE UPDATE ON "
               "cover_letters FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "application_emails",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", pg.UUID(as_uuid=True)),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("to_email", sa.String(320)),
        sa.Column("to_name", sa.String(200)),
        sa.Column("cc", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("bcc", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("body_format", sa.String(8), nullable=False,
                  server_default=sa.text("'plain'")),
        sa.Column("attachment_refs", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'draft'")),
        sa.Column("provider", sa.String(16)),
        sa.Column("provider_message_id", sa.String(200)),
        sa.Column("sent_at", _TS),
        sa.Column("send_error", sa.Text),
        sa.Column("generation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "body_format in ('plain','html')",
            name="application_emails_body_format_valid",
        ),
        sa.CheckConstraint(
            "status in ('draft','awaiting_approval','approved','sending','sent','failed','canceled')",
            name="application_emails_status_valid",
        ),
    )
    op.create_index("ix_application_emails_user", "application_emails",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_application_emails_job", "application_emails", ["job_id"])
    op.execute("CREATE TRIGGER trg_application_emails_set_updated_at BEFORE UPDATE ON "
               "application_emails FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_application_emails_set_updated_at "
               "ON application_emails")
    op.drop_table("application_emails")
    op.execute("DROP TRIGGER IF EXISTS trg_cover_letters_set_updated_at ON cover_letters")
    op.drop_table("cover_letters")
```

- [ ] **Step 4: `tests/models/test_application_models.py`** (DB-gated, CI-only)

```python
"""CoverLetter / ApplicationEmail model round-trip -- DB integration, CI-deferred."""
from __future__ import annotations

from app.models.application import ApplicationEmail, CoverLetter
from app.models.job import Job
from app.models.user import User


async def test_cover_letter_and_application_email_round_trip(db_session):
    u = User(email="app-docs@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()

    letter = CoverLetter(
        user_id=u.id, job_id=j.id, content="Dear Hiring Team,\n\nI am excited to apply.",
        created_by="mana_ai",
    )
    db_session.add(letter)
    await db_session.flush()
    assert letter.tone == "professional"
    assert letter.version == 1
    assert letter.content_json == {}
    assert letter.created_at is not None

    email = ApplicationEmail(
        user_id=u.id, job_id=j.id, subject="Application: Backend Engineer",
        body="Please find my résumé and cover letter attached.",
    )
    db_session.add(email)
    await db_session.flush()
    assert email.status == "draft"
    assert email.body_format == "plain"
    assert email.cc == []
    assert email.to_email is None
```

- [ ] **Step 5: gate + verify migration**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run alembic heads`
Expected: `lint-imports` still `3 kept, 0 broken`; `pytest --collect-only` error-free; `alembic heads` prints exactly `0012_application_documents (head)`. Do NOT run `test_application_models.py` locally (DB-gated).

```bash
git add backend/app/models/application.py backend/app/models/__init__.py backend/alembic/versions/0012_application_documents.py backend/tests/models/test_application_models.py
git commit -m "feat(applications): cover_letters + application_emails tables (migration 0012)"
```

---

## Task 5: agent nodes (`cover_letter`, `letter_claim_validator`, `email_draft`) + supervisor routing

**Files:** Create `backend/app/domain/agents/nodes/cover_letter.py`, `backend/app/domain/agents/nodes/letter_claim_validator.py`, `backend/app/domain/agents/nodes/email_draft.py`, `backend/tests/domain/agents/test_nodes_application.py`. Modify `backend/app/domain/agents/nodes/supervisor.py`, `backend/app/domain/agents/nodes/__init__.py`, `backend/app/domain/agents/state.py`, `backend/app/domain/agents/blocks.py`.

**Interfaces:**
- Consumes: `write_cover_letter` (Task 2), `draft_email` (Task 3), `CoverLetter`/`ApplicationEmail` (Task 4), `_summarise_profile`/`_summarise_job` (already-existing private helpers in `app.domain.agents.nodes.resume_tailoring` — reused, not duplicated, per spec §4), `TailoringService.get_version` (existing, Phase 8a), `JobService.get`/`ProfileService.load_full`/`.list_skills` (existing).
- Produces: `cover_letter(state, *, deps) -> dict` sets `state["cover_letter_id"]`; `letter_claim_validator(state, *, deps) -> dict` (never halts); `email_draft(state, *, deps) -> dict` sets `state["email_draft_id"]`. `supervisor` routes `goal == "prepare_application"` to `"resume_tailoring"`.

- [ ] **Step 1: `app/domain/agents/state.py`** — extend `NODE_ORDER` (insert before `"respond"`):
```python
NODE_ORDER: tuple[str, ...] = (
    "supervisor",
    "job_research",
    "job_retrieval",
    "match_analysis",
    "skill_gap",
    "recommendation",
    "resume_tailoring",
    "claim_validator",
    "cover_letter",
    "letter_claim_validator",
    "email_draft",
    "respond",
)
```

- [ ] **Step 2: `app/domain/agents/blocks.py`** — widen `ApplicationDraftBlock`:
```python
class ApplicationDraftBlock(BaseModel):
    kind: Literal["application_draft"] = "application_draft"
    application_id: uuid.UUID | None = None
    resume_version_id: uuid.UUID | None = None
    cover_letter_id: uuid.UUID | None = None
    email_draft_id: uuid.UUID | None = None
```
(Everything else in the file — the union, `dump_blocks`, all other block classes — is unchanged.)

- [ ] **Step 3: `app/domain/agents/nodes/supervisor.py`** — add one branch (order doesn't matter relative to the existing three, but keep them together):
```python
    if goal == "tailor_resume":
        return {"_route": "resume_tailoring", "_summary": "Routing: tailor a résumé"}
    if goal == "prepare_application":
        return {"_route": "resume_tailoring", "_summary": "Routing: prepare an application"}
    if goal == "understand_job":
```

- [ ] **Step 4: `app/domain/agents/nodes/cover_letter.py`**

```python
"""``cover_letter`` -- write a grounded cover letter for the tailored résumé + job."""

import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.nodes.resume_tailoring import _summarise_job, _summarise_profile
from app.domain.agents.state import ManaState
from app.domain.generation.cover_letter import write_cover_letter
from app.domain.generation.service import GenerationService
from app.domain.jobs.service import JobService
from app.domain.profile.service import ProfileService
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.version_service import TailoringService
from app.models.application import CoverLetter

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def cover_letter(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    job_id = state["inputs"]["job_id"]
    version_id = state.get("tailored_resume_version_id")
    if not version_id:
        return {
            "status": "halted",
            "error": "no tailored résumé to write a cover letter from",
            "_summary": "Tailor a résumé first",
        }

    version = await TailoringService(deps.session).get_version(
        deps.user_id, uuid.UUID(version_id)
    )
    tailored = ResumeExtraction.model_validate(version.content)

    job = await JobService(deps.session).get(deps.user_id, job_id)
    profile, sections = await ProfileService(deps.session).load_full(deps.user_id)
    skills = await ProfileService(deps.session).list_skills(deps.user_id)
    profile_summary = _summarise_profile(profile, sections, skills)
    job_brief = _summarise_job(job)

    gen = GenerationService(deps.llm)
    draft, meta = await write_cover_letter(
        gen=gen, base=tailored, profile_summary=profile_summary, job_brief=job_brief
    )

    state["budget"]["llm_calls_made"] = state["budget"].get("llm_calls_made", 0) + 1
    state["budget"]["cost_usd"] = state["budget"].get("cost_usd", 0.0) + meta.cost_usd

    letter = CoverLetter(
        user_id=deps.user_id,
        job_id=job_id,
        resume_version_id=version.id,
        content=draft.content,
        content_json={
            "paragraphs": [p for p in draft.content.split("\n\n") if p.strip()]
        },
        generation_meta={
            "model": meta.model,
            "provider": meta.provider,
            "prompt_version": meta.prompt_version,
            "prompt_hash": meta.prompt_hash,
            "input_tokens": meta.input_tokens,
            "output_tokens": meta.output_tokens,
            "cost_usd": meta.cost_usd,
            "claim_validation": meta.claim_validation,
        },
        created_by="mana_ai",
    )
    deps.session.add(letter)
    await deps.session.flush()

    checked = meta.claim_validation.get("checked", 0)
    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="cover_letter",
        action_key="wrote_cover_letter",
        summary=f"Wrote a cover letter for {job.title} — {checked} claims checked",
    )

    return {
        "cover_letter_id": str(letter.id),
        "_summary": "Cover letter draft ready",
        "_detail": {"claim_validation": meta.claim_validation},
    }
```

- [ ] **Step 5: `app/domain/agents/nodes/letter_claim_validator.py`**

```python
"""``letter_claim_validator`` -- re-run claim validation over the cover letter
``cover_letter`` just wrote, purely to give the trace a discrete step.

Deterministic. Never halts the run. Peer of ``claim_validator`` (résumé) --
see that file's docstring for why this is a separate node rather than one
function parameterized by artifact type: LangGraph node registration is
per-name, and each node's job here is intentionally single-purpose.
"""

import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.generation.cover_letter import _collect_sources
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.tailoring import ClaimValidator, _split_sentences
from app.domain.resume.version_service import TailoringService
from app.models.application import CoverLetter

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def letter_claim_validator(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    letter_id = state.get("cover_letter_id")
    if not letter_id:
        return {"_summary": "Nothing to validate", "_step_status": "skipped_fresh"}

    letter = await deps.session.get(CoverLetter, uuid.UUID(letter_id))
    if letter is None or letter.resume_version_id is None:
        return {"_summary": "Nothing to validate", "_step_status": "skipped_fresh"}

    version = await TailoringService(deps.session).get_version(
        deps.user_id, letter.resume_version_id
    )
    tailored = ResumeExtraction.model_validate(version.content)
    sources = _collect_sources(tailored, "", "")
    report = ClaimValidator(sources).check(_split_sentences(letter.content))

    if report.passed:
        summary = f"All {report.checked} claims grounded"
        status = "ok"
    else:
        summary = f"{len(report.unsupported)} of {report.checked} claims need a source"
        status = "warning"

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="letter_claim_validator",
        action_key="validated_letter_claims",
        summary=summary,
        status=status,
    )

    return {"_summary": summary, "_step_status": "ok"}
```

- [ ] **Step 6: `app/domain/agents/nodes/email_draft.py`**

```python
"""``email_draft`` -- draft the application email from the cover letter."""

import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.generation.email_draft import draft_email
from app.domain.generation.service import GenerationService
from app.domain.jobs.service import JobService
from app.models.application import ApplicationEmail, CoverLetter
from app.models.user import User

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def email_draft(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    letter_id = state.get("cover_letter_id")
    if not letter_id:
        return {
            "status": "halted",
            "error": "no cover letter to draft an email from",
            "_summary": "Write a cover letter first",
        }

    letter = await deps.session.get(CoverLetter, uuid.UUID(letter_id))
    if letter is None:
        return {
            "status": "halted",
            "error": "no cover letter to draft an email from",
            "_summary": "Write a cover letter first",
        }

    job = await JobService(deps.session).get(deps.user_id, letter.job_id)
    user = await deps.session.get(User, deps.user_id)
    applicant_name = (user.full_name if user else "") or ""

    gen = GenerationService(deps.llm)
    draft, meta = await draft_email(
        gen=gen,
        job_title=job.title,
        company=job.company or "",
        applicant_name=applicant_name,
        cover_letter_content=letter.content,
    )

    state["budget"]["llm_calls_made"] = state["budget"].get("llm_calls_made", 0) + 1
    state["budget"]["cost_usd"] = state["budget"].get("cost_usd", 0.0) + meta.cost_usd

    email = ApplicationEmail(
        user_id=deps.user_id,
        job_id=letter.job_id,
        subject=draft.subject,
        body=draft.body,
        generation_meta={
            "model": meta.model,
            "provider": meta.provider,
            "prompt_version": meta.prompt_version,
            "prompt_hash": meta.prompt_hash,
            "input_tokens": meta.input_tokens,
            "output_tokens": meta.output_tokens,
            "cost_usd": meta.cost_usd,
        },
    )
    deps.session.add(email)
    await deps.session.flush()

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="email_draft",
        action_key="drafted_email",
        summary=f"Drafted an application email for {job.title}",
    )

    return {
        "email_draft_id": str(email.id),
        "_summary": "Application email draft ready",
    }
```

- [ ] **Step 7: `app/domain/agents/nodes/__init__.py`** — add the 3 new imports + `__all__` entries, keeping alphabetical order:
```python
from app.domain.agents.nodes.claim_validator import claim_validator
from app.domain.agents.nodes.cover_letter import cover_letter
from app.domain.agents.nodes.email_draft import email_draft
from app.domain.agents.nodes.halted import halted
from app.domain.agents.nodes.job_research import job_research
from app.domain.agents.nodes.job_retrieval import job_retrieval
from app.domain.agents.nodes.letter_claim_validator import letter_claim_validator
from app.domain.agents.nodes.match_analysis import match_analysis
from app.domain.agents.nodes.recommendation import recommendation
from app.domain.agents.nodes.respond import respond
from app.domain.agents.nodes.resume_tailoring import resume_tailoring
from app.domain.agents.nodes.skill_gap import skill_gap
from app.domain.agents.nodes.supervisor import supervisor

__all__ = [
    "claim_validator",
    "cover_letter",
    "email_draft",
    "halted",
    "job_research",
    "job_retrieval",
    "letter_claim_validator",
    "match_analysis",
    "recommendation",
    "respond",
    "resume_tailoring",
    "skill_gap",
    "supervisor",
]
```

- [ ] **Step 8: `tests/domain/agents/test_nodes_application.py`** (pure)

```python
from app.domain.agents.nodes.supervisor import supervisor


async def test_supervisor_routes_prepare_application():
    out = await supervisor(
        {"goal": "prepare_application", "inputs": {"job_id": "j1"}}, deps=object()
    )
    assert out["_route"] == "resume_tailoring"


async def test_cover_letter_halts_with_no_tailored_resume():
    from app.domain.agents.nodes.cover_letter import cover_letter

    out = await cover_letter(
        {"inputs": {"job_id": "j1"}, "tailored_resume_version_id": None}, deps=object()
    )
    assert out["status"] == "halted"


async def test_letter_claim_validator_skips_with_no_cover_letter():
    from app.domain.agents.nodes.letter_claim_validator import letter_claim_validator

    out = await letter_claim_validator({"cover_letter_id": None}, deps=object())
    assert out["_step_status"] == "skipped_fresh"


async def test_email_draft_halts_with_no_cover_letter():
    from app.domain.agents.nodes.email_draft import email_draft

    out = await email_draft({"cover_letter_id": None}, deps=object())
    assert out["status"] == "halted"
```

- [ ] **Step 9: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/agents/test_nodes_application.py`
Expected: all PASS (4 tests).

```bash
git add backend/app/domain/agents/state.py backend/app/domain/agents/blocks.py backend/app/domain/agents/nodes/supervisor.py backend/app/domain/agents/nodes/cover_letter.py backend/app/domain/agents/nodes/letter_claim_validator.py backend/app/domain/agents/nodes/email_draft.py backend/app/domain/agents/nodes/__init__.py backend/tests/domain/agents/test_nodes_application.py
git commit -m "feat(agents): cover_letter + letter_claim_validator + email_draft nodes; prepare_application routing"
```

---

## Task 6: graph wiring + `respond` block

**Files:** Modify `backend/app/domain/agents/graph.py`, `backend/app/domain/agents/nodes/respond.py`, `backend/tests/domain/agents/test_graph_tailor.py` (rename/extend as needed — see Step 3). Create `backend/tests/domain/agents/test_graph_prepare_application.py`.

**Interfaces:**
- Consumes: the 3 new nodes (Task 5), `ApplicationDraftBlock` (Task 5 Step 2).
- Produces: `build_graph` wires `resume_tailoring → claim_validator → {respond | cover_letter} → letter_claim_validator → email_draft → respond`, chosen by `state["goal"]`.

- [ ] **Step 1: `graph.py`** — add the 3 imports, add the 3 nodes to the guard-wrapped loop, replace the `claim_validator → respond` edge with a goal-aware branch, and add the new edges:

```python
from app.domain.agents.nodes.cover_letter import cover_letter
from app.domain.agents.nodes.email_draft import email_draft
from app.domain.agents.nodes.letter_claim_validator import letter_claim_validator
```
(add alongside the existing node imports, alphabetically)

In `build_graph`, the guard-wrapped node list becomes:
```python
    for name, fn in [
        ("job_research", job_research),
        ("job_retrieval", job_retrieval),
        ("match_analysis", match_analysis),
        ("skill_gap", skill_gap),
        ("recommendation", recommendation),
        ("resume_tailoring", resume_tailoring),
        ("claim_validator", claim_validator),
        ("cover_letter", cover_letter),
        ("letter_claim_validator", letter_claim_validator),
        ("email_draft", email_draft),
        ("respond", respond),
    ]:
```
(Note: `resume_tailoring` and `claim_validator` were already in this list per Phase 8a — this shows the full intended list so you can see exactly where the 3 new entries go, right after `claim_validator` and before `respond`.)

Replace the existing `claim_validator → respond` conditional edge:
```python
    g.add_conditional_edges(
        "claim_validator",
        _halt_or("respond"),
        {"respond": "respond", "halted": "halted"},
    )
```
with a goal-aware router (add this function near `_halt_or`, above `build_graph`):
```python
def _after_resume_claim_check(state: ManaState) -> str:
    if state.get("status") in {"halted", "error"}:
        return "halted"
    return "cover_letter" if state.get("goal") == "prepare_application" else "respond"
```
and the edge:
```python
    g.add_conditional_edges(
        "claim_validator",
        _after_resume_claim_check,
        {"cover_letter": "cover_letter", "respond": "respond", "halted": "halted"},
    )
    g.add_conditional_edges(
        "cover_letter",
        _halt_or("letter_claim_validator"),
        {"letter_claim_validator": "letter_claim_validator", "halted": "halted"},
    )
    g.add_conditional_edges(
        "letter_claim_validator",
        _halt_or("email_draft"),
        {"email_draft": "email_draft", "halted": "halted"},
    )
    g.add_conditional_edges(
        "email_draft",
        _halt_or("respond"),
        {"respond": "respond", "halted": "halted"},
    )
```
(`g.add_edge("respond", END)` and everything after it is unchanged.)

Refresh the module docstring's node/worker-node counts: "ten nodes"/"eight worker nodes" → "thirteen nodes"/"eleven worker nodes" (count `supervisor` + `halted` as the two non-worker nodes; the rest — job_research, job_retrieval, match_analysis, skill_gap, recommendation, resume_tailoring, claim_validator, cover_letter, letter_claim_validator, email_draft, respond — are the 11 guard-wrapped worker nodes).

- [ ] **Step 2: `respond.py`** — add a new FIRST branch, checked before the existing `tailored_resume_version_id` branch (a `prepare_application` run has both set, and the fuller outcome should win):
```python
    blocks: list[BaseModel]
    if state.get("email_draft_id"):
        text = (
            "Your cover letter and application email are ready — take a look "
            "before you send anything."
        )
        blocks = [
            TextBlock(markdown=text),
            ApplicationDraftBlock(
                resume_version_id=uuid.UUID(state["tailored_resume_version_id"])
                if state.get("tailored_resume_version_id")
                else None,
                cover_letter_id=uuid.UUID(state["cover_letter_id"])
                if state.get("cover_letter_id")
                else None,
                email_draft_id=uuid.UUID(state["email_draft_id"]),
            ),
        ]
    elif state.get("tailored_resume_version_id"):
        text = (
            "Here's a version of your résumé tuned for this role — open it to "
            "see what changed."
        )
        blocks = [
            TextBlock(markdown=text),
            ResumeSuggestionBlock(
                suggestion_id=uuid.UUID(state["tailored_resume_version_id"])
            ),
        ]
    elif not state.get("retrieved_jobs"):
```
(the `elif not state.get("retrieved_jobs"):` line and everything below it is the existing code, unchanged — just re-indented under the new `if`/`elif` chain instead of the old `if`/`elif`. Also add `ApplicationDraftBlock` to the import from `app.domain.agents.blocks`.)

- [ ] **Step 3: add a sibling graph-shape test.** `tests/domain/agents/test_graph_tailor.py` (confirmed current content: 2 tests, `_route_from_supervisor` + a source-text check for `"resume_tailoring"`/`"claim_validator"` inside `build_graph`) is untouched and unaffected by this task's edits — both node names still appear in `build_graph`'s source after Step 1's changes. Add a NEW sibling file rather than editing it, keeping each goal's shape assertions independent:
```python
from app.domain.agents.graph import _after_resume_claim_check


def test_after_resume_claim_check_routes_prepare_application_to_cover_letter():
    state = {"goal": "prepare_application", "status": "running"}
    assert _after_resume_claim_check(state) == "cover_letter"


def test_after_resume_claim_check_routes_tailor_resume_to_respond():
    state = {"goal": "tailor_resume", "status": "running"}
    assert _after_resume_claim_check(state) == "respond"


def test_after_resume_claim_check_routes_halted_state_to_halted():
    state = {"goal": "prepare_application", "status": "halted"}
    assert _after_resume_claim_check(state) == "halted"
```

- [ ] **Step 4: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/agents/test_graph_prepare_application.py tests/domain/agents/test_graph_tailor.py`
Expected: all PASS (3 new tests + whatever `test_graph_tailor.py` already has, unchanged).

```bash
git add backend/app/domain/agents/graph.py backend/app/domain/agents/nodes/respond.py backend/tests/domain/agents/test_graph_prepare_application.py
git commit -m "feat(agents): wire prepare_application's cover_letter -> email_draft chain into the graph"
```

---

## Task 7: generation eval suite + CI + API dispatch

**Files:** Create `backend/eval/datasets/generation/golden_v1.jsonl`, `backend/eval/suites/generation.py`, `backend/tests/eval/test_generation_suite.py`. Modify `backend/eval/thresholds.py`, `backend/eval/run.py`, `backend/app/api/v1/schemas/eval.py`, `backend/app/api/v1/eval.py`, `.github/workflows/ci.yml`.

**Interfaces:**
- Consumes: `write_cover_letter`/`draft_email` (Tasks 2-3), `ClaimValidator`/`_split_sentences` (Task 1), `GenerationService`, `EvalRun`/`EvalResult` models (existing).
- Produces: `run_generation_suite(session, *, llm_provider, write_db, git_sha) -> GenerationEvalReport`; `python -m eval.run generation --write-db`; `EvalRunIn.suite: Literal["retrieval", "generation"]`.

- [ ] **Step 1: `eval/thresholds.py`** — append:
```python
GROUNDEDNESS_FLOOR = 1.0
KEYWORD_COVERAGE_FLOOR = 0.0
QUALITY_GROUNDEDNESS = 0.85
QUALITY_KEYWORD_COVERAGE = 0.50
```
(Calibration note — put this as a comment above the four constants: under `LLM_PROVIDER=fake`, `write_cover_letter`/`draft_email` always produce empty strings, so `checked=0` claim lines → `ClaimReport.supported_ratio` is `1.0` by definition, and zero keyword matches → coverage `0.0`. These floors are exactly that — a plumbing check, not a quality gate. `QUALITY_*` are for a future manual run against a real provider.)

- [ ] **Step 2: `eval/datasets/generation/golden_v1.jsonl`** — one JSON object per line (confirmed format, verified directly against `eval/datasets/retrieval/golden_v1.jsonl` while writing this plan):
```
{"id": "gen-1", "resume": {"full_name": "A. Dev", "summary": "Backend engineer focused on Python and distributed systems.", "skills": ["python", "postgresql", "kubernetes"], "experiences": [{"company": "Acme", "title": "Senior Backend Engineer", "description": "Owned the payments platform.", "highlights": ["Reduced p99 latency by 40 percent", "Migrated the datastore to Postgres"], "tech": ["python", "postgresql"]}]}, "job": {"title": "Senior Backend Engineer", "company": "Globex", "description": "Build resilient payments infrastructure at scale.", "required_skills": [{"label": "Python"}, {"label": "PostgreSQL"}, {"label": "Kubernetes"}]}, "expected_keywords": ["python", "postgresql", "kubernetes", "globex"]}
{"id": "gen-2", "resume": {"full_name": "B. Chen", "summary": "Frontend engineer specializing in React and design systems.", "skills": ["react", "typescript", "accessibility"], "experiences": [{"company": "Initech", "title": "Frontend Engineer", "description": "Built the design system.", "highlights": ["Shipped a component library used by 12 teams"], "tech": ["react", "typescript"]}]}, "job": {"title": "Senior Frontend Engineer", "company": "Umbrella Corp", "description": "Own our design system and component library.", "required_skills": [{"label": "React"}, {"label": "TypeScript"}, {"label": "Design Systems"}]}, "expected_keywords": ["react", "typescript", "umbrella"]}
{"id": "gen-3", "resume": {"full_name": "C. Okoye", "summary": "Data engineer building ETL pipelines on Spark and Airflow.", "skills": ["python", "spark", "airflow"], "experiences": [{"company": "Hooli", "title": "Data Engineer", "description": "Built the ingestion pipeline.", "highlights": ["Cut pipeline runtime from 6 hours to 40 minutes"], "tech": ["spark", "airflow"]}]}, "job": {"title": "Senior Data Engineer", "company": "Soylent", "description": "Scale our batch and streaming data platform.", "required_skills": [{"label": "Spark"}, {"label": "Airflow"}, {"label": "Python"}]}, "expected_keywords": ["spark", "airflow", "python", "soylent"]}
{"id": "gen-4", "resume": {"full_name": "D. Singh", "summary": "ML engineer focused on recommendation systems.", "skills": ["python", "pytorch", "sql"], "experiences": [{"company": "Wonka Industries", "title": "ML Engineer", "description": "Owned the recommendation model.", "highlights": ["Improved click-through rate by 18 percent"], "tech": ["pytorch", "python"]}]}, "job": {"title": "Machine Learning Engineer", "company": "Stark Industries", "description": "Build our next-generation recommendation engine.", "required_skills": [{"label": "PyTorch"}, {"label": "Python"}, {"label": "Recommendation Systems"}]}, "expected_keywords": ["pytorch", "python", "stark"]}
```

- [ ] **Step 3: `eval/suites/generation.py`**

```python
"""Generation eval suite: score write_cover_letter + draft_email against a
hand-authored golden set.

Under ``LLM_PROVIDER=fake`` every generated field is empty (see
``FakeLLMProvider``), so the deterministic metrics trivially clear their
default-tier floors (see ``thresholds.py``'s calibration note) -- this suite
proves the pipeline runs end to end and persists an EvalRun/EvalResult, not
that the writing is any good. The LLM-judge leg runs every time (proving that
plumbing works too) but is never gated in CI (see thresholds.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.generation.cover_letter import write_cover_letter
from app.domain.generation.email_draft import draft_email
from app.domain.generation.service import GenerationService
from app.domain.llm.factory import get_llm_provider
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.tailoring import ClaimValidator, _split_sentences
from app.models.eval import EvalResult, EvalRun
from app.models.user import User
from eval.thresholds import (
    GROUNDEDNESS_FLOOR,
    KEYWORD_COVERAGE_FLOOR,
    QUALITY_GROUNDEDNESS,
    QUALITY_KEYWORD_COVERAGE,
)

GOLDEN_PATH = Path(__file__).parent.parent / "datasets" / "generation" / "golden_v1.jsonl"
EVAL_USER_EMAIL = "eval-runner@mana.internal"


class _JudgeVerdict(BaseModel):
    score: float
    rationale: str


@dataclass
class CaseScore:
    case_id: str
    groundedness: float
    keyword_coverage: float
    judge_score: float
    passed: bool


@dataclass
class GenerationEvalReport:
    aggregate: dict[str, float]
    cases: list[CaseScore]
    passed: bool


def load_golden() -> list[dict[str, Any]]:
    lines = GOLDEN_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


async def ensure_eval_user(session: AsyncSession) -> User:
    user = (
        await session.execute(select(User).where(User.email == EVAL_USER_EMAIL))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=EVAL_USER_EMAIL,
            password_hash="x",  # noqa: S106  eval user never authenticates
            full_name="Eval Runner",
        )
        session.add(user)
        await session.flush()
    return user


async def run_generation_suite(
    session: AsyncSession, *, llm_provider: str, write_db: bool, git_sha: str
) -> GenerationEvalReport:
    await ensure_eval_user(session)
    llm = get_llm_provider(get_settings())
    gen = GenerationService(llm)

    golden = load_golden()
    cases: list[CaseScore] = []
    for case in golden:
        resume = ResumeExtraction.model_validate(case["resume"])
        job = case["job"]
        job_brief = f"{job['title']} at {job['company']}\n{job['description']}"

        letter, letter_meta = await write_cover_letter(
            gen=gen, base=resume, profile_summary="", job_brief=job_brief
        )
        email, _email_meta = await draft_email(
            gen=gen, job_title=job["title"], company=job["company"],
            applicant_name=resume.full_name or "", cover_letter_content=letter.content,
        )

        groundedness = letter_meta.claim_validation.get("supported_ratio", 1.0)

        combined = f"{letter.content}\n{email.subject}\n{email.body}".lower()
        expected = case.get("expected_keywords", [])
        matched = [kw for kw in expected if kw.lower() in combined]
        keyword_coverage = len(matched) / len(expected) if expected else 1.0

        judge_res = await gen.generate(
            system="Rate how well this application material fits the job, 0-1.",
            user=f"Job: {job_brief}\n\nCover letter:\n{letter.content}\n\nEmail:\n{email.body}",
            schema=_JudgeVerdict,
            prompt_version="judge-1",
            max_tokens=200,
        )
        verdict = _JudgeVerdict.model_validate(judge_res.structured)

        passed = groundedness >= GROUNDEDNESS_FLOOR and keyword_coverage >= KEYWORD_COVERAGE_FLOOR
        cases.append(
            CaseScore(
                case_id=case["id"],
                groundedness=groundedness,
                keyword_coverage=keyword_coverage,
                judge_score=verdict.score,
                passed=passed,
            )
        )

    n = len(cases) or 1
    aggregate = {
        "groundedness": sum(c.groundedness for c in cases) / n,
        "keyword_coverage": sum(c.keyword_coverage for c in cases) / n,
        "judge_score": sum(c.judge_score for c in cases) / n,
    }
    is_quality = llm_provider not in {"fake", ""}
    groundedness_floor = QUALITY_GROUNDEDNESS if is_quality else GROUNDEDNESS_FLOOR
    coverage_floor = QUALITY_KEYWORD_COVERAGE if is_quality else KEYWORD_COVERAGE_FLOOR
    report_passed = (
        aggregate["groundedness"] >= groundedness_floor
        and aggregate["keyword_coverage"] >= coverage_floor
    )

    if write_db:
        now = datetime.now(tz=UTC)
        run = EvalRun(
            suite="generation",
            dataset_ref="datasets/generation/golden_v1.jsonl",
            dataset_version="v1",
            git_sha=git_sha,
            provider=llm_provider,
            model_ids={},
            config={},
            metrics=aggregate,
            status="passed" if report_passed else "failed",
            started_at=now,
            ended_at=now,
        )
        session.add(run)
        await session.flush()
        for case, score in zip(golden, cases, strict=True):
            session.add(
                EvalResult(
                    eval_run_id=run.id,
                    case_id=score.case_id,
                    input={"job": case["job"]},
                    expected={"expected_keywords": case.get("expected_keywords", [])},
                    actual={
                        "groundedness": score.groundedness,
                        "keyword_coverage": score.keyword_coverage,
                    },
                    scores={
                        "groundedness": score.groundedness,
                        "keyword_coverage": score.keyword_coverage,
                        "judge_score": score.judge_score,
                    },
                    passed=score.passed,
                    judge_meta={"rationale_len": 0},
                )
            )
        await session.flush()

    return GenerationEvalReport(aggregate=aggregate, cases=cases, passed=report_passed)
```

(`get_llm_provider(settings: Settings) -> LLMProvider` and `Settings.llm_provider` are both confirmed real signatures — verified directly against `app/domain/llm/factory.py` and `app/core/config.py` while writing this plan, mirroring exactly how `eval/suites/retrieval.py` calls `get_embeddings_provider(get_settings())`.)

- [ ] **Step 4: `eval/run.py`** — widen the CLI:
```python
    parser.add_argument("suite", choices=["retrieval", "generation"])
```
and after the existing `if`-free single-suite call, branch on `args.suite`:
```python
    git_sha = os.environ.get("GITHUB_SHA", "dev")[:40]
    async with AsyncSessionLocal() as session:
        if args.suite == "retrieval":
            report = await run_retrieval_suite(
                session, provider=args.provider, write_db=args.write_db, git_sha=git_sha
            )
        else:
            report = await run_generation_suite(
                session, llm_provider=args.provider, write_db=args.write_db, git_sha=git_sha
            )
        if args.write_db:
            await session.commit()

    if args.suite == "retrieval":
        quality = args.provider == "voyage"
        floors = {
            "recall_at_10": QUALITY_RECALL_AT_10 if quality else RECALL_AT_10,
            "mrr": QUALITY_MRR if quality else MRR,
            "ndcg_at_10": QUALITY_NDCG_AT_10 if quality else NDCG_AT_10,
        }
    else:
        quality = args.provider not in {"fake", ""}
        floors = {
            "groundedness": QUALITY_GROUNDEDNESS if quality else GROUNDEDNESS_FLOOR,
            "keyword_coverage": QUALITY_KEYWORD_COVERAGE if quality else KEYWORD_COVERAGE_FLOOR,
        }
    print(f"{'metric':<16} {'value':>8} {'threshold':>10} {'pass':>6}")
    for name, floor in floors.items():
        v = report.aggregate[name]
        print(f"{name:<16} {v:>8.3f} {floor:>10.3f} {('yes' if v >= floor else 'NO'):>6}")
    for name, v in report.aggregate.items():
        if name not in floors:
            print(f"{name:<16} {v:>8.3f} {'-':>10} {'-':>6}")
```
`--provider` here doubles as the LLM provider name for the generation suite (default still `os.environ.get("EMBEDDINGS_PROVIDER", "fake")` for retrieval; for generation, pass `--provider fake` explicitly in CI — see Step 6 — since the relevant env var is `LLM_PROVIDER`, not `EMBEDDINGS_PROVIDER`). Add the two imports:
```python
from eval.suites.generation import run_generation_suite
from eval.thresholds import (
    GROUNDEDNESS_FLOOR,
    KEYWORD_COVERAGE_FLOOR,
    MRR,
    NDCG_AT_10,
    QUALITY_GROUNDEDNESS,
    QUALITY_KEYWORD_COVERAGE,
    QUALITY_MRR,
    QUALITY_NDCG_AT_10,
    QUALITY_RECALL_AT_10,
    RECALL_AT_10,
)
```

- [ ] **Step 5: `app/api/v1/schemas/eval.py` + `app/api/v1/eval.py`** — `EvalRunIn`'s only field is `suite: Literal["retrieval"]` (confirmed current content); widen it to:
```python
class EvalRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite: Literal["retrieval", "generation"]
```
In `eval.py`'s `create_eval_run`, replace the hardcoded call with a dispatch:
```python
@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_eval_run(body: EvalRunIn, db: DbDep, _: CurrentAdmin) -> EvalRunOut:
    git_sha = os.environ.get("GITHUB_SHA", "dev")[:40]
    if body.suite == "retrieval":
        await run_retrieval_suite(
            db, provider=get_settings().embeddings_provider, write_db=True, git_sha=git_sha,
        )
    else:
        await run_generation_suite(
            db, llm_provider=get_settings().llm_provider, write_db=True, git_sha=git_sha,
        )
    run = (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.suite == body.suite)
            .order_by(EvalRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one()
    return _run_out(run)
```
(add `from eval.suites.generation import run_generation_suite` to the imports; `Settings.llm_provider` is confirmed real — see Step 3's note.)

- [ ] **Step 6: `.github/workflows/ci.yml`** — after the existing `uv run python -m eval.run retrieval --write-db` step in the `eval` job, add:
```yaml
      - run: uv run python -m eval.run generation --write-db --provider fake
        env:
          DATABASE_URL: postgresql+asyncpg://mana:mana@localhost:5432/mana_test
          EMBEDDINGS_PROVIDER: fake
          LLM_PROVIDER: fake
          JWT_SECRET: ci-not-secret
          REDIS_URL: redis://localhost:6379/0
```

- [ ] **Step 7: `tests/eval/test_generation_suite.py`** (DB-gated, CI-only)

```python
"""Generation eval suite -- DB integration, CI-deferred."""
from __future__ import annotations

from sqlalchemy import select

from app.models.eval import EvalResult, EvalRun
from eval.suites.generation import load_golden, run_generation_suite


async def test_run_generation_suite_persists_a_passed_run_under_fake(db_session):
    report = await run_generation_suite(
        db_session, llm_provider="fake", write_db=True, git_sha="test-sha"
    )
    assert report.passed is True
    assert 0.0 <= report.aggregate["keyword_coverage"] <= 1.0

    run = (
        await db_session.execute(
            select(EvalRun).where(EvalRun.suite == "generation")
        )
    ).scalar_one()
    assert run.status == "passed"

    results = (
        await db_session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == run.id)
        )
    ).scalars().all()
    assert len(results) == len(load_golden())
```

- [ ] **Step 8: gate**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: all clean (`lint-imports` still `3 kept, 0 broken`; collection error-free). Do NOT run `test_generation_suite.py` locally (DB-gated).

```bash
git add backend/eval backend/app/api/v1/schemas/eval.py backend/app/api/v1/eval.py backend/tests/eval/test_generation_suite.py .github/workflows/ci.yml
git commit -m "feat(eval): generation suite -- groundedness + keyword coverage + judge plumbing"
```

---

## Task 8: full-chain worker integration test (SUBAGENT REVIEW — DB-gated, multi-file integration)

**Files:** Create `backend/tests/worker/test_prepare_application_task.py`.

**Interfaces:**
- Consumes: everything from Tasks 1-7. This task writes no new production code — it is the DB-gated proof that the whole `prepare_application` chain actually runs end to end through `run_agent`, mirroring `tests/worker/test_tailoring_task.py` exactly (same fixtures, same `_ctx`/`_fake_redis_cls` helpers — copy them, this repo's convention is one self-contained copy per worker test file, not a shared test-fixture module).

- [ ] **Step 1: read `tests/worker/test_tailoring_task.py` in full first** — this task's file is structurally identical to it (same `_ctx`, `_fake_redis_cls`, `_seed`-style helper, same `run_agent({}, run_id)` call, same `AiSession`/`AgentStep`/`AiAction` assertions), just with `goal="prepare_application"` and assertions extended through the cover-letter/email chain.

- [ ] **Step 2: `tests/worker/test_prepare_application_task.py`**

```python
"""run_agent preparing a full application (résumé -> letter -> email) --
DB integration, CI-deferred."""
from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.agents.service import AgentService
from app.models.ai import AgentStep, AiAction, AiSession, Message
from app.models.application import ApplicationEmail, CoverLetter
from app.models.job import Job
from app.models.resume import Resume
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.worker.tasks.agent import run_agent


@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


def _fake_redis_cls(fake_redis):
    return type("R", (), {"from_url": staticmethod(lambda *a, **k: fake_redis)})


async def _seed(db_session, email):
    u = User(email=email, password_hash="x", full_name="A. Dev")
    db_session.add(u)
    await db_session.flush()
    r = Resume(
        user_id=u.id, file_ref="r.pdf", content_type="application/pdf", size_bytes=100,
        status="extracted", is_primary=True,
        extraction={
            "full_name": "A. Dev", "summary": "Backend engineer.",
            "skills": ["python"], "experiences": [],
        },
    )
    r.confirmed_at = datetime.now(UTC)
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add_all([r, j])
    await db_session.flush()
    return u, r, j


async def test_run_agent_prepares_a_full_application(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr("app.worker.tasks.agent._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis))

    u, resume, job = await _seed(db_session, "prepare-app@x.com")
    svc = AgentService(db_session)
    sess = await svc.create_session(u.id, kind="agent_run")
    run_id = await svc.start_run(
        u.id, sess.id, goal="prepare_application",
        inputs={"job_id": str(job.id), "resume_id": str(resume.id)},
    )

    out = await run_agent({}, run_id)
    assert out == {"run_id": run_id, "status": "completed"}

    version = (
        await db_session.execute(
            select(ResumeVersion).where(
                ResumeVersion.resume_id == resume.id, ResumeVersion.kind == "ai_tailored"
            )
        )
    ).scalar_one()

    letter = (
        await db_session.execute(
            select(CoverLetter).where(CoverLetter.resume_version_id == version.id)
        )
    ).scalar_one()
    assert letter.job_id == job.id

    email = (
        await db_session.execute(
            select(ApplicationEmail).where(ApplicationEmail.job_id == job.id)
        )
    ).scalar_one()
    assert email.status == "draft"

    msg = (
        await db_session.execute(
            select(Message).where(Message.ai_session_id == sess.id, Message.role == "assistant")
        )
    ).scalar_one()
    assert "application_draft" in [b["kind"] for b in msg.blocks]

    steps = (
        await db_session.execute(select(AgentStep).where(AgentStep.run_id == run_id))
    ).scalars().all()
    assert {
        "resume_tailoring", "claim_validator", "cover_letter",
        "letter_claim_validator", "email_draft",
    } <= {st.node for st in steps}

    actions = (
        await db_session.execute(select(AiAction).where(AiAction.run_id == run_id))
    ).scalars().all()
    assert {a.action_key for a in actions} >= {
        "tailored_resume", "wrote_cover_letter", "drafted_email",
    }

    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "completed"
```

- [ ] **Step 3: gate**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: all clean; the new test collects but is NOT run locally (DB-gated).

```bash
git add backend/tests/worker/test_prepare_application_task.py
git commit -m "test(agents): full prepare_application chain -- résumé, letter, email, blocks (DB-gated)"
```

---

## Task 9: verification + whole-branch review + completion report + squash + push + CI

Controller-only, no subagent. Mirror the Phase 8a/8b closeout exactly:
1. Run the full local gate on the branch tip: ruff, mypy, lint-imports (confirm still `3 kept, 0 broken`), `pytest -q --collect-only` (error-free), `alembic heads` (confirm single head `0012_application_documents`).
2. Run every pure test suite added/modified across all 8 tasks (skip every DB-gated file: `test_application_models.py`, `test_prepare_application_task.py`, `test_generation_suite.py`).
3. Whole-branch review (inline — this phase has one subagent-reviewed task, Task 8, already covered there; the rest follow the lean policy for small/pure backend tasks): read the full commit range diff, scan for TODO/FIXME/stubs, trace type consistency end to end (`ClaimValidator.check()`'s new signature through every call site; `ApplicationDraftBlock`'s new optional fields through `respond.py`; `state["cover_letter_id"]`/`state["email_draft_id"]` through nodes → graph → respond).
4. Write the completion report into this plan file (§ what changed, why, files changed, how to test, regression check — baseline test/mypy-file/import-contract counts before vs after, as-built rulings, deviations, not-verified-here) — same structure as Phase 8a's and Phase 8b's completion reports.
5. Squash to `main` (reconstruct via `git checkout <branch-tip> -- <paths>` + commit per file-group, OR fast-forward if the task commits are already clean — check `git diff --stat main <branch-tip>` against the sum of task commits first) into ~6-8 readable commits.
6. Push, watch CI (the `eval` job specifically — this is the first phase to add a second CI step to it; make sure both `retrieval` and `generation` eval steps go green, and watch for the SSE/ASGITransport-style hang class of failure per the standing memory note, though this phase touches no SSE/streaming code so it should not recur).
7. `finishing-a-development-branch`: delete the branch + `.superpowers/sdd/2026-09-05-phase-9-cover-letter-email-generation/`.

---

## Completion report

**Status: shipped.** All 8 implementation tasks executed via subagent-driven-development (fresh implementer per task — Sonnet for 7, Haiku for the one purely-mechanical transcription task — with dedicated subagent review for the two high-risk tasks, migration and the DB-gated integration test, and inline controller review for the rest), on branch `phase-9-cover-letter-email-generation` off `main@f38fa07`.

**What changed:** `ClaimValidator.check()` generalized to take `claim_lines: list[str]` instead of a `ResumeExtraction`, unlocking reuse beyond résumé tailoring. Two new generation primitives — `write_cover_letter()` (reprompt-loop + claim validation, mirrors `tailor_resume`) and `draft_email()` (single schema-constrained call, no reprompt loop). Two new tables (`cover_letters`, `application_emails`, migration `0012`). Three new agent nodes — `cover_letter`, `letter_claim_validator`, `email_draft` — extending the existing `resume_tailoring → claim_validator` chain behind a new `prepare_application` goal (the literal already existed, unused, from Phase 7a). `ApplicationDraftBlock` widened with three optional artifact-id fields. A `generation` eval suite (groundedness + keyword-coverage, deterministic; an LLM-judge leg that always runs but is never CI-gated) added alongside the existing `retrieval` suite, wired into `/eval`'s API and the CI `eval` job. 32 files changed, +1232/-47, 8 commits (`538da33`..`ea3808a`).

**Key design decisions (all recorded as rulings in the spec addendum before any task was dispatched):**
- `prepare_application`'s chain this phase is `resume_tailoring → claim_validator → cover_letter → letter_claim_validator → email_draft → respond` — deliberately NOT the master spec's full theoretical chain (no `job_research`/`match_analysis`/`skill_gap` re-entry, no `application_prep`/`human_approval`/`email_external_action`). Phase 10 extends the *same* goal's graph further; it does not introduce a new goal.
- No UI, no new API trigger endpoint this phase — verified instead via a worker-level DB integration test (Task 8), mirroring `test_tailoring_task.py` exactly. The real "Prepare Application" button is Phase 10's Builder UI.
- `ApplicationDraftBlock.application_id` became optional (`None` until Phase 10's `applications` table exists) and gained `resume_version_id`/`cover_letter_id`/`email_draft_id` — the same reuse-a-declared-stub pattern Phase 8a used for `ResumeSuggestionBlock`.
- The `generation` eval suite's CI floors (`GROUNDEDNESS_FLOOR=1.0`, `KEYWORD_COVERAGE_FLOOR=0.0`) are calibrated to exactly what `FakeLLMProvider`'s empty-string stubs produce — a plumbing check, not a quality gate, exactly like every other fake-provider test in this repo. `QUALITY_*` floors are reserved for a future manual run against a real provider.
- `cover_letters`/`application_emails`' optional cross-reference columns (`job_id` on the latter is required; `application_id`, `resume_version_id`, `supersedes_id` are all nullable) carry no FK constraint, mirroring the `resume_versions.application_id` precedent from migration `0011` exactly.

**Process notes:** one task (Task 4, the migration) and one task (Task 8, the DB-gated integration test) got dedicated subagent reviews per the high-risk policy — both PASS, zero blocking findings. Every other task was small/pure enough for inline controller review. Every implementer that reported a deviation from the brief's verbatim code did so correctly and necessarily (a ruff line-length split in Task 4, a `str | None` → `str` coercion + a stale test fixture value in Task 5, three lint/type fixes in Task 7) — each was independently verified against the real source before being accepted; none required a fix-round re-dispatch.

**Regression check:** local gate green throughout — ruff/mypy/lint-imports (still `3 kept, 0 broken`) clean at every task boundary and on final `main`. Backend test count: 379 (baseline at branch start, `f38fa07`, verified directly in an isolated worktree) → 393 (branch tip). mypy source-file count: 142 → 148. `alembic heads`: single head, `0011_resume_tailoring` → `0012_application_documents`. All 23 pure tests added/modified across the 8 tasks pass on the squashed `main` tip; every DB-gated test (`test_application_models.py`, `test_prepare_application_task.py`, `test_generation_suite.py`) collects error-free locally and is left for CI.

**CI:** pending — this phase adds a second step to the `eval` CI job (`python -m eval.run generation --write-db --provider fake`) for the first time; watched to green as part of this closeout (see the CI run link once pushed).

**Not verified here (flagged, not addressed):** the `generation` eval suite's LLM-judge leg was never exercised against a real LLM provider (only `fake`, which trivially stubs `score`/`rationale` to zero-values) — its plumbing runs and persists a score, but the score itself has no meaning until run manually against a real provider. The reprompt-loop path in both `write_cover_letter` and the résumé `claim_validator` node is not exercised by the DB-gated integration test either, since `FakeLLMProvider`'s empty output trivially passes claim validation on the first attempt. Everything Phase 10 owns (`applications`, `approval_requests`, `application_prep`, `human_approval`, `email_external_action`, any UI) remains untouched, as scoped.
