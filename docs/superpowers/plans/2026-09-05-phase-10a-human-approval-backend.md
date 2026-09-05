# Phase 10a — Human approval workflow (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop from a drafted résumé + cover letter + email to an actual, human-approved, sent application: `application_prep` (deterministic assembly + hash) → `human_approval` (pause the graph, wait for a person) → `email_external_action` (assert approved + hash match, send via a sandboxed `EmailSender`, audit).

**Architecture:** Three new agent nodes extend the `prepare_application` chain past `email_draft`. `human_approval` uses LangGraph's `interrupt()`/`Command(resume=...)` to pause and later resume the SAME graph thread — the first use of this mechanism in the codebase, so `run_agent`'s astream-drive logic is refactored into a shared helper used by both the existing `run_agent` (fresh start) and a new `resume_agent` worker task (resume). Two new tables (`applications`, `approval_requests`), two new minimal API routers (`/applications`, `/approvals`), and a console-only `EmailSender` abstraction.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, LangGraph 1.2.11, ARQ + Redis, pydantic-settings.

**Spec:** `docs/superpowers/specs/2026-09-05-phase-10a-human-approval-backend.md` — read this first. It has 12 rulings (R1-R12) resolving every ambiguity below, several backed by direct verification against the installed `langgraph==1.2.11` (exception hierarchies, `StateSnapshot`/`Command`/`interrupt` signatures) — do not re-derive these, they are settled.

## Global Constraints

- **No frontend, no UI.** Phase 10b, separate cycle.
- `LLM_PROVIDER=fake` / `EMBEDDINGS_PROVIDER=fake` in CI and every test.
- **No local Postgres/Redis.** DB-backed tests ERROR locally and run only in CI. Local gates: `"$UV" run ruff check .` / `"$UV" run mypy app` / `"$UV" run lint-imports` / `"$UV" run pytest -q --collect-only` (error-free) + the pure suites named per task. `$UV` = `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`.
- Alembic chain `…→0012_application_documents→0013_applications_approvals`, single head. Mirror `0011_resume_tailoring.py`/`0012_application_documents.py`'s style exactly. `postgresql_where=sa.text(...)` for the partial unique index — the exact syntax (both ORM `Index(..., unique=True, postgresql_where=text(...))` and migration `op.create_index(..., unique=True, postgresql_where=sa.text(...))`) is copied verbatim from the live `job_matches` precedent (`app/models/match.py`, `alembic/versions/0008_matches.py`) in this plan's own tasks below — already verified against the installed SQLAlchemy version.
- **`human_approval` is a RAW node** (not `guard()`-wrapped) — R1. `guard()` gets one defensive line — R2. Both are load-bearing correctness facts, not style choices: `interrupt()` raises `GraphInterrupt` (`Exception` subclass), and `guard()`'s bare `except Exception` would otherwise swallow it.
- `ManaState.status` Literal gains `"awaiting_approval"` — the DB column (`ai_sessions.status` CHECK constraint) already allows it (Phase 7a); no migration needed for that specific fact.
- No reject→revise loop (R8), no edits/reconfirm (R9), no `/approvals/{id}/cancel` (R11), no SMTP/Resend (R12), no `/applications` list/patch/notes/timeline (R10) — all explicitly out of scope, all extension points a later phase can add without breaking this one's contracts.
- Node budget bumps are INLINE, no helper (standing convention). All tuning values are module-level named constants.
- `mypy` strict. Every def fully annotated. No new import-linter contract — stays `3 kept, 0 broken`.

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `backend/app/core/config.py` | Modify | + `email_provider: str = "console"` |
| `backend/app/domain/email/__init__.py` · `types.py` · `sender.py` · `factory.py` | Create | `EmailMessage`, `EmailSendResult`, `EmailSender`, `ConsoleEmailSender`, `get_email_sender` |
| `backend/app/domain/agents/budget.py` | Modify | `guard()` re-raises `GraphBubbleUp` |
| `backend/app/domain/agents/state.py` | Modify | `status` Literal + `approval_request_id` key + `NODE_ORDER` |
| `backend/app/models/application.py` | Modify | + `Application`, `ApprovalRequest` |
| `backend/app/models/__init__.py` | Modify | (no change — `application` module already imported, Phase 9) |
| `backend/alembic/versions/0013_applications_approvals.py` | Create | `applications`, `approval_requests` tables + triggers + partial unique index |
| `backend/app/domain/agents/nodes/application_prep.py` | Create | deterministic assembly + hash |
| `backend/app/domain/agents/nodes/human_approval.py` | Create | interrupt + decision routing (raw) |
| `backend/app/domain/agents/nodes/email_external_action.py` | Create | assert + send + audit |
| `backend/app/domain/agents/nodes/respond.py` | Modify | `approval_action` / "sent" branches |
| `backend/app/domain/agents/nodes/__init__.py` | Modify | re-export the 3 new nodes |
| `backend/app/domain/agents/graph.py` | Modify | `AgentDeps.email_sender`; register 3 nodes (2 guarded, 1 raw); new edges + raw-route function |
| `backend/app/domain/agents/service.py` | Modify | `mark_awaiting_approval`, `resume_run`, `RESUME_JOB` |
| `backend/app/worker/tasks/agent.py` | Modify | extract `_drive()`; add `resume_agent` |
| `backend/app/worker/main.py` | Modify | register `resume_agent` |
| `backend/app/api/v1/schemas/applications.py` · `applications.py` | Create | `POST /applications`, `GET /applications/{id}` |
| `backend/app/api/v1/schemas/approvals.py` · `approvals.py` | Create | `GET /approvals`, `GET /approvals/{id}`, `POST /approvals/{id}` |
| `backend/app/api/v1/router.py` | Modify | register the 2 new routers |
| tests | Create | `tests/domain/email/test_sender.py` · `tests/domain/agents/test_budget_interrupt.py` · `tests/domain/agents/test_nodes_approval.py` · `tests/domain/agents/test_graph_approval.py` · `tests/models/test_application_approval_models.py` (DB) · `tests/worker/test_resume_agent.py` (DB) · `tests/api/test_applications.py` (DB) · `tests/api/test_approvals.py` (DB) |

---

## Task 1: `EmailSender` abstraction + config

**Files:** Create `backend/app/domain/email/__init__.py`, `types.py`, `sender.py`, `factory.py`, `backend/tests/domain/email/__init__.py`, `backend/tests/domain/email/test_sender.py`. Modify `backend/app/core/config.py`.

**Interfaces:**
- Produces: `EmailMessage`, `EmailSendResult`, `EmailSender` (Protocol), `ConsoleEmailSender`, `get_email_sender(settings) -> EmailSender`; `Settings.email_provider: str = "console"`.

- [ ] **Step 1: `app/core/config.py`** — add, near `doc_render_enabled`:
```python
    email_provider: str = "console"
```

- [ ] **Step 2: `app/domain/email/__init__.py`** — empty.

- [ ] **Step 3: `app/domain/email/types.py`**
```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailMessage:
    to_email: str
    to_name: str | None
    subject: str
    body: str
    body_format: str = "plain"


@dataclass(frozen=True)
class EmailSendResult:
    provider: str
    provider_message_id: str
```

- [ ] **Step 4: `app/domain/email/sender.py`**
```python
from __future__ import annotations

import uuid
from typing import Protocol

from app.core.logging import get_logger
from app.domain.email.types import EmailMessage, EmailSendResult

log = get_logger("email")


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> EmailSendResult: ...


class ConsoleEmailSender:
    """Sandboxed default -- logs the message, sends nothing over the network."""

    async def send(self, message: EmailMessage) -> EmailSendResult:
        log.info(
            "email_send_console",
            to_email=message.to_email,
            subject=message.subject,
            body_len=len(message.body),
        )
        return EmailSendResult(
            provider="console", provider_message_id=f"console-{uuid.uuid4().hex}"
        )
```

- [ ] **Step 5: `app/domain/email/factory.py`**
```python
from __future__ import annotations

from app.core.config import Settings
from app.domain.email.sender import ConsoleEmailSender, EmailSender


def get_email_sender(settings: Settings) -> EmailSender:
    if settings.email_provider == "console":
        return ConsoleEmailSender()
    raise NotImplementedError(f"{settings.email_provider} email adapter lands in a later phase")
```

- [ ] **Step 6: `tests/domain/email/test_sender.py`**
```python
from app.domain.email.factory import get_email_sender
from app.domain.email.sender import ConsoleEmailSender
from app.domain.email.types import EmailMessage


def test_get_email_sender_defaults_to_console(monkeypatch):
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.email_provider == "console"
    assert isinstance(get_email_sender(s), ConsoleEmailSender)


def test_get_email_sender_raises_for_unbuilt_providers():
    from app.core.config import Settings

    s = Settings(_env_file=None, email_provider="smtp")
    import pytest

    with pytest.raises(NotImplementedError):
        get_email_sender(s)


async def test_console_sender_returns_a_synthetic_message_id():
    sender = ConsoleEmailSender()
    result = await sender.send(
        EmailMessage(to_email="a@b.com", to_name="A", subject="Hi", body="Hello")
    )
    assert result.provider == "console"
    assert result.provider_message_id.startswith("console-")
```

If `Settings(_env_file=None, ...)` is not the right way to construct a one-off `Settings` instance in this codebase's test style, check how `tests/domain/generation/test_imports.py` (Phase 8a) constructs `Settings` for its `doc_render_enabled` default-value test and mirror that exact pattern instead.

- [ ] **Step 7: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/email/test_sender.py`
Expected: all PASS (3 tests).

```bash
git add backend/app/core/config.py backend/app/domain/email backend/tests/domain/email
git commit -m "feat(email): EmailSender abstraction -- console-only sandboxed default"
```

---

## Task 2: `guard()` interrupt passthrough + `ManaState` widening

**Files:** Modify `backend/app/domain/agents/budget.py`, `backend/app/domain/agents/state.py`, `backend/tests/domain/agents/test_state.py`. Create `backend/tests/domain/agents/test_budget_interrupt.py`.

**Interfaces:**
- Produces: `guard()` no longer mis-catches `GraphInterrupt`; `ManaState.status` includes `"awaiting_approval"`; `ManaState.approval_request_id: str | None` (new key); `NODE_ORDER` gains the 3 new node names.

- [ ] **Step 1: `app/domain/agents/budget.py`** — add the import and the passthrough clause. Add to the imports:
```python
from langgraph.errors import GraphBubbleUp
```
In `guard()`'s wrapper, the existing:
```python
        try:
            partial = await fn(state)
        except Exception as exc:
```
becomes:
```python
        try:
            partial = await fn(state)
        except GraphBubbleUp:
            # LangGraph's own control-flow exceptions (interrupt(), etc.) must
            # propagate untouched -- see the Phase 10a spec R2. No node this
            # phase raises this from inside a guard()-wrapped node (human_approval
            # is registered raw specifically to avoid needing this), but the
            # fix belongs here defensively for any future one that does.
            raise
        except Exception as exc:
```
(Everything else in `guard()` is unchanged.)

- [ ] **Step 2: `app/domain/agents/state.py`** — widen the status Literal and add the new state key, and extend `NODE_ORDER`:
```python
    status: Literal[
        "running", "awaiting_approval", "completed", "rejected", "halted", "error"
    ]
```
(was `Literal["running", "completed", "rejected", "halted", "error"]`)

Add `approval_request_id: str | None` to `ManaState` right after the existing `application_id: str | None` line.

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
    "application_prep",
    "human_approval",
    "email_external_action",
    "respond",
)
```

- [ ] **Step 3: `tests/domain/agents/test_state.py`** — this file currently asserts `NODE_ORDER[0] == "supervisor" and NODE_ORDER[-1] == "respond"` (both still true after Step 2) — read it to confirm no other hardcoded length/content assertion breaks; if it only asserts those two boundary facts, no change is needed to this file.

- [ ] **Step 4: `tests/domain/agents/test_budget_interrupt.py`**
```python
import pytest
from langgraph.errors import GraphInterrupt

from app.domain.agents.budget import guard
from app.domain.agents.budget import new_budget, budget_now


async def _raises_interrupt(state):
    raise GraphInterrupt("paused")


async def test_guard_lets_graph_interrupt_propagate():
    wrapped = guard("some_node", _raises_interrupt)
    state = {
        "budget": dict(new_budget(now=budget_now())),
        "step_log": [],
        "stop_requested": False,
    }
    with pytest.raises(GraphInterrupt):
        await wrapped(state)
```

- [ ] **Step 5: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/agents/test_state.py tests/domain/agents/test_budget_interrupt.py`
Expected: all PASS.

```bash
git add backend/app/domain/agents/budget.py backend/app/domain/agents/state.py backend/tests/domain/agents/test_budget_interrupt.py
git commit -m "fix(agents): guard() lets GraphInterrupt/GraphBubbleUp propagate; ManaState gains awaiting_approval"
```

---

## Task 3: migration `0013` + `Application`/`ApprovalRequest` models (SUBAGENT REVIEW — high-risk)

**Files:** Modify `backend/app/models/application.py`. Create `backend/alembic/versions/0013_applications_approvals.py`, `backend/tests/models/test_application_approval_models.py`.

**Interfaces:**
- Produces: `Application` (table `applications`), `ApprovalRequest` (table `approval_requests`); single alembic head `0013_applications_approvals`.

- [ ] **Step 1: append to `app/models/application.py`** (same module as `CoverLetter`/`ApplicationEmail` — do not create a new file; this module's docstring/imports already cover "application documents/records"):
```python
class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status in ('saved','preparing','awaiting_approval','applied',"
            "'interview','offer','rejected','withdrawn')",
            name="applications_status_valid",
        ),
        CheckConstraint("source in ('user','mana_ai')", name="applications_source_valid"),
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_user_updated", "user_id", text("updated_at DESC")),
        Index("ix_applications_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK on job_id/resume_version_id/cover_letter_id/application_email_id/
    # ai_session_id: loose optional cross-references, matching every other
    # forward reference in this schema (resume_versions.application_id, etc.).
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cover_letter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    application_email_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'preparing'")
    )
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'mana_ai'")
    )
    ai_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    applied_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_status_change_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "action_type in ('send_application_email')",
            name="approval_requests_action_type_valid",
        ),
        CheckConstraint(
            "status in ('pending','approved','rejected','superseded','expired')",
            name="approval_requests_status_valid",
        ),
        Index("ix_approval_requests_user_status", "user_id", "status"),
        Index(
            "uq_approval_requests_run_pending",
            "run_id", "action_type",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK on application_id/ai_session_id/decided_by -- same loose-reference
    # convention as Application above.
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ai_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'send_application_email'")
    )
    payload_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
```

Add the two new imports this needs (`Decimal` from `decimal`, `Numeric` from `sqlalchemy`) to the file's existing import block — check the file's current imports first (from Phase 9: `TIMESTAMP, CheckConstraint, ForeignKey, Index, String, Text, text` from `sqlalchemy`; `ARRAY, JSONB, UUID` from `sqlalchemy.dialects.postgresql`; `Mapped, mapped_column` from `sqlalchemy.orm`; `dt`, `uuid`, `Any` already imported at module level) and only add what's missing (`Decimal`, `Numeric`).

- [ ] **Step 2: `alembic/versions/0013_applications_approvals.py`**
```python
"""applications + approval_requests tables

Revision ID: 0013_applications_approvals
Revises: 0012_application_documents
Create Date: 2026-09-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0013_applications_approvals"
down_revision = "0012_application_documents"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("resume_version_id", pg.UUID(as_uuid=True)),
        sa.Column("cover_letter_id", pg.UUID(as_uuid=True)),
        sa.Column("application_email_id", pg.UUID(as_uuid=True)),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'preparing'")),
        sa.Column("match_score", sa.Numeric(5, 2)),
        sa.Column("source", sa.String(16), nullable=False,
                  server_default=sa.text("'mana_ai'")),
        sa.Column("ai_session_id", pg.UUID(as_uuid=True)),
        sa.Column("applied_at", _TS),
        sa.Column("last_status_change_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("notes", sa.Text),
        sa.Column("deleted_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "status in ('saved','preparing','awaiting_approval','applied',"
            "'interview','offer','rejected','withdrawn')",
            name="applications_status_valid",
        ),
        sa.CheckConstraint(
            "source in ('user','mana_ai')", name="applications_source_valid"
        ),
    )
    op.create_index("ix_applications_user_status", "applications", ["user_id", "status"])
    op.create_index("ix_applications_user_updated", "applications",
                    ["user_id", sa.text("updated_at DESC")])
    op.create_index("ix_applications_job", "applications", ["job_id"])
    op.execute("CREATE TRIGGER trg_applications_set_updated_at BEFORE UPDATE ON "
               "applications FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "approval_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False,
                  server_default=sa.text("'send_application_email'")),
        sa.Column("payload_snapshot", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("decided_by", pg.UUID(as_uuid=True)),
        sa.Column("decided_at", _TS),
        sa.Column("decision_note", sa.Text),
        sa.Column("expires_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "action_type in ('send_application_email')",
            name="approval_requests_action_type_valid",
        ),
        sa.CheckConstraint(
            "status in ('pending','approved','rejected','superseded','expired')",
            name="approval_requests_status_valid",
        ),
    )
    op.create_index("ix_approval_requests_user_status", "approval_requests",
                    ["user_id", "status"])
    op.create_index("uq_approval_requests_run_pending", "approval_requests",
                    ["run_id", "action_type"], unique=True,
                    postgresql_where=sa.text("status = 'pending'"))
    op.execute("CREATE TRIGGER trg_approval_requests_set_updated_at BEFORE UPDATE ON "
               "approval_requests FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_approval_requests_set_updated_at "
               "ON approval_requests")
    op.drop_table("approval_requests")
    op.execute("DROP TRIGGER IF EXISTS trg_applications_set_updated_at ON applications")
    op.drop_table("applications")
```

- [ ] **Step 3: `tests/models/test_application_approval_models.py`** (DB-gated, CI-only)
```python
"""Application / ApprovalRequest model round-trip -- DB integration, CI-deferred."""
from __future__ import annotations

from app.models.application import Application, ApprovalRequest
from app.models.job import Job
from app.models.user import User


async def test_application_and_approval_request_round_trip(db_session):
    u = User(email="app-approval@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()

    app_row = Application(user_id=u.id, job_id=j.id)
    db_session.add(app_row)
    await db_session.flush()
    assert app_row.status == "preparing"
    assert app_row.source == "mana_ai"
    assert app_row.last_status_change_at is not None

    req = ApprovalRequest(
        user_id=u.id, application_id=app_row.id, ai_session_id=app_row.id,
        run_id="run-1", payload_hash="a" * 64,
    )
    db_session.add(req)
    await db_session.flush()
    assert req.action_type == "send_application_email"
    assert req.status == "pending"
    assert req.payload_snapshot == {}


async def test_only_one_pending_approval_request_per_run(db_session):
    from sqlalchemy.exc import IntegrityError
    import pytest

    u = User(email="app-approval-2@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    app_row = Application(user_id=u.id, job_id=j.id)
    db_session.add(app_row)
    await db_session.flush()

    db_session.add(ApprovalRequest(
        user_id=u.id, application_id=app_row.id, ai_session_id=app_row.id,
        run_id="run-dup", payload_hash="a" * 64,
    ))
    await db_session.flush()
    db_session.add(ApprovalRequest(
        user_id=u.id, application_id=app_row.id, ai_session_id=app_row.id,
        run_id="run-dup", payload_hash="b" * 64,
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 4: gate + verify migration**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run alembic heads`
Expected: `lint-imports` still `3 kept, 0 broken`; collection error-free; `alembic heads` prints exactly `0013_applications_approvals (head)`. Do NOT run the DB-gated test locally.

```bash
git add backend/app/models/application.py backend/alembic/versions/0013_applications_approvals.py backend/tests/models/test_application_approval_models.py
git commit -m "feat(applications): applications + approval_requests tables (migration 0013)"
```

---

## Task 4: `application_prep` node

**Files:** Create `backend/app/domain/agents/nodes/application_prep.py`, `backend/tests/domain/agents/test_nodes_approval.py` (this task creates the file; Tasks 5-6 extend it).

**Interfaces:**
- Consumes: `CoverLetter`, `ApplicationEmail` (existing, Phase 9), `Application`, `ApprovalRequest` (Task 3), `JobService.get` (existing).
- Produces: `application_prep(state, *, deps) -> dict` sets `state["application_id"]`, `state["approval_request_id"]`.

- [ ] **Step 1: `app/domain/agents/nodes/application_prep.py`**
```python
"""``application_prep`` -- deterministic assembly of the approval snapshot.

Builds a hashable snapshot of everything the human is about to approve
(job, cover letter, drafted email) and persists it as a new ``Application`` +
a pending ``ApprovalRequest``. No LLM call. Runs once (guard()-wrapped,
normal node -- unlike ``human_approval``, this never re-executes on resume).
"""

import hashlib
import json
import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.jobs.service import JobService
from app.models.application import Application, ApplicationEmail, ApprovalRequest, CoverLetter

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


def _build_snapshot(
    job_title: str, company: str, resume_version_id: str | None,
    letter: CoverLetter, email: ApplicationEmail,
) -> dict[str, Any]:
    return {
        "job": {"title": job_title, "company": company},
        "resume_version_id": resume_version_id,
        "cover_letter": {"id": str(letter.id), "content": letter.content},
        "email": {
            "id": str(email.id), "to_email": email.to_email, "to_name": email.to_name,
            "subject": email.subject, "body": email.body,
        },
    }


def _hash_snapshot(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def application_prep(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    job_id = state["inputs"]["job_id"]
    letter_id = state.get("cover_letter_id")
    email_id = state.get("email_draft_id")
    if not letter_id or not email_id:
        return {
            "status": "halted",
            "error": "no cover letter/email to prepare an application from",
            "_summary": "Draft a cover letter and email first",
        }

    letter = await deps.session.get(CoverLetter, uuid.UUID(letter_id))
    email = await deps.session.get(ApplicationEmail, uuid.UUID(email_id))
    if letter is None or email is None:
        return {
            "status": "halted",
            "error": "no cover letter/email to prepare an application from",
            "_summary": "Draft a cover letter and email first",
        }

    job = await JobService(deps.session).get(deps.user_id, job_id)
    resume_version_id = state.get("tailored_resume_version_id")

    snapshot = _build_snapshot(job.title or "", job.company or "", resume_version_id, letter, email)
    payload_hash = _hash_snapshot(snapshot)

    application = Application(
        user_id=deps.user_id,
        job_id=job_id,
        resume_version_id=uuid.UUID(resume_version_id) if resume_version_id else None,
        cover_letter_id=letter.id,
        application_email_id=email.id,
        status="awaiting_approval",
        source="mana_ai",
        ai_session_id=deps.session_id,
    )
    deps.session.add(application)
    await deps.session.flush()

    approval = ApprovalRequest(
        user_id=deps.user_id,
        application_id=application.id,
        ai_session_id=deps.session_id,
        run_id=deps.run_id,
        payload_snapshot=snapshot,
        payload_hash=payload_hash,
    )
    deps.session.add(approval)
    await deps.session.flush()

    # Back-fill the forward references left None when these rows were written.
    letter.application_id = application.id
    email.application_id = application.id
    await deps.session.flush()

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="application_prep",
        action_key="prepared_application",
        summary=f"Prepared your application for {job.title}",
        entity_type="application",
        entity_id=application.id,
    )

    return {
        "application_id": str(application.id),
        "approval_request_id": str(approval.id),
        "_summary": "Application ready for your review",
    }
```

- [ ] **Step 2: `tests/domain/agents/test_nodes_approval.py`** (pure — this file is extended by Tasks 5 and 6)
```python
from app.domain.agents.nodes.application_prep import application_prep


async def test_application_prep_halts_with_no_cover_letter():
    out = await application_prep(
        {"inputs": {"job_id": "j1"}, "cover_letter_id": None, "email_draft_id": None},
        deps=object(),
    )
    assert out["status"] == "halted"


async def test_application_prep_halts_with_letter_but_no_email():
    out = await application_prep(
        {"inputs": {"job_id": "j1"}, "cover_letter_id": "11111111-1111-1111-1111-111111111111", "email_draft_id": None},
        deps=object(),
    )
    assert out["status"] == "halted"
```

- [ ] **Step 3: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/agents/test_nodes_approval.py`
Expected: all PASS (2 tests).

```bash
git add backend/app/domain/agents/nodes/application_prep.py backend/tests/domain/agents/test_nodes_approval.py
git commit -m "feat(agents): application_prep -- deterministic approval snapshot + hash"
```

---

## Task 5: `human_approval` node (raw)

**Files:** Create `backend/app/domain/agents/nodes/human_approval.py`. Modify `backend/tests/domain/agents/test_nodes_approval.py`.

**Interfaces:**
- Consumes: `interrupt` (`langgraph.types`), `ApprovalRequest` (Task 3).
- Produces: `human_approval(state, *, deps) -> dict` — **not** wrapped by `guard()` when registered in Task 7's graph wiring. Sets `_route` to `"email_external_action"` or `"halted"`.

- [ ] **Step 1: `app/domain/agents/nodes/human_approval.py`**
```python
"""``human_approval`` -- pause the graph and wait for a person.

Registered RAW in the graph (never guard()-wrapped) -- see the Phase 10a
spec R1/R2: interrupt() raises GraphInterrupt, which guard()'s bare
except Exception would otherwise catch and mis-report as a node error.

interrupt() re-executes this node's body from the top on resume (R3) --
everything before the interrupt() call must be a harmless repeat. The one
DB read here (re-fetching the ApprovalRequest row) is pure and idempotent;
its result is only used to build the interrupt's payload, and is discarded
on resume in favor of the actual resume value.

No reject-then-revise loop this phase (R8): rejecting is terminal.
"""

import uuid
from typing import TYPE_CHECKING, Any

from langgraph.types import interrupt

from app.domain.agents.state import ManaState
from app.models.application import ApprovalRequest

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def human_approval(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    approval_id = state["approval_request_id"]
    _ = await deps.session.get(ApprovalRequest, uuid.UUID(approval_id))  # harmless re-read

    decision_payload = interrupt({"approval_id": approval_id})

    decision = decision_payload.get("decision") if isinstance(decision_payload, dict) else None
    if decision == "approve":
        return {"approval": decision_payload, "_route": "email_external_action"}
    if decision == "reject":
        return {
            "status": "rejected",
            "approval": decision_payload,
            "_route": "halted",
            "_summary": "You rejected this application",
        }
    return {
        "status": "error",
        "error": "unrecognized approval decision",
        "_route": "halted",
        "_summary": "Something went wrong with your decision",
    }
```

- [ ] **Step 2: extend `tests/domain/agents/test_nodes_approval.py`** — add:
```python
async def test_human_approval_routes_approve_to_email_external_action():
    from unittest.mock import AsyncMock

    from app.domain.agents.nodes.human_approval import human_approval

    deps = AsyncMock()
    deps.session.get = AsyncMock(return_value=None)

    # human_approval calls interrupt(), which raises GraphInterrupt when not
    # running inside a real graph invocation with a resume value queued.
    # Test the routing logic directly instead, bypassing interrupt(): this is
    # the same "test the pure decision logic, not the LangGraph plumbing"
    # split already used elsewhere (e.g. claim_validator's node vs its
    # ClaimValidator primitive). Patch interrupt() to return a canned value.
    import app.domain.agents.nodes.human_approval as mod

    mod_interrupt = mod.interrupt
    mod.interrupt = lambda payload: {"decision": "approve"}
    try:
        out = await human_approval(
            {"approval_request_id": "11111111-1111-1111-1111-111111111111"}, deps=deps
        )
    finally:
        mod.interrupt = mod_interrupt
    assert out["_route"] == "email_external_action"


async def test_human_approval_routes_reject_to_halted():
    from unittest.mock import AsyncMock

    import app.domain.agents.nodes.human_approval as mod

    deps = AsyncMock()
    deps.session.get = AsyncMock(return_value=None)

    mod_interrupt = mod.interrupt
    mod.interrupt = lambda payload: {"decision": "reject"}
    try:
        out = await mod.human_approval(
            {"approval_request_id": "11111111-1111-1111-1111-111111111111"}, deps=deps
        )
    finally:
        mod.interrupt = mod_interrupt
    assert out["status"] == "rejected"
    assert out["_route"] == "halted"
```

If monkeypatching a module-level name by direct reassignment (rather than `monkeypatch.setattr`) causes any test-isolation issue in this codebase's pytest setup, use `monkeypatch.setattr(mod, "interrupt", lambda payload: {...})` instead (pytest's built-in `monkeypatch` fixture, auto-reverted after the test) — check how other tests in `tests/domain/agents/` patch module attributes and mirror that convention exactly.

- [ ] **Step 3: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/agents/test_nodes_approval.py`
Expected: all PASS (4 tests).

```bash
git add backend/app/domain/agents/nodes/human_approval.py backend/tests/domain/agents/test_nodes_approval.py
git commit -m "feat(agents): human_approval -- interrupt + approve/reject routing (raw node)"
```

---

## Task 6: `email_external_action` node

**Files:** Create `backend/app/domain/agents/nodes/email_external_action.py`. Modify `backend/tests/domain/agents/test_nodes_approval.py`.

**Interfaces:**
- Consumes: `EmailSender`/`EmailMessage` (Task 1), `audit()` (`app.core.audit`, existing), `Application`/`ApprovalRequest`/`ApplicationEmail`/`CoverLetter` (Task 3 / Phase 9), the same `_build_snapshot`/`_hash_snapshot` functions from `application_prep.py` (Task 4) — imported, not duplicated.
- Produces: `email_external_action(state, *, deps) -> dict`.

- [ ] **Step 1: `app/domain/agents/nodes/email_external_action.py`**
```python
"""``email_external_action`` -- assert approved + hash match, then send.

The only side-effecting step in the whole graph. Re-verifies the payload
hash against the CURRENT rows (not just trusting the earlier snapshot) --
a mismatch halts without sending, per the Phase 10a "done when" bar.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.audit import audit
from app.domain.agents.nodes.application_prep import _build_snapshot, _hash_snapshot
from app.domain.agents.state import ManaState
from app.domain.email.types import EmailMessage
from app.domain.jobs.service import JobService
from app.models.application import Application, ApplicationEmail, ApprovalRequest, CoverLetter

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def email_external_action(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    approval_id = state["approval_request_id"]
    approval = await deps.session.get(ApprovalRequest, uuid.UUID(approval_id))
    if approval is None or approval.status != "approved":
        return {
            "status": "halted",
            "error": "approval not in an approved state",
            "_summary": "This application hasn't been approved",
        }

    application = await deps.session.get(Application, approval.application_id)
    letter = await deps.session.get(CoverLetter, application.cover_letter_id)
    email = await deps.session.get(ApplicationEmail, application.application_email_id)
    if application is None or letter is None or email is None:
        return {
            "status": "halted",
            "error": "application record incomplete",
            "_summary": "This application is missing required data",
        }

    job = await JobService(deps.session).get(deps.user_id, application.job_id)
    current_snapshot = _build_snapshot(
        job.title or "", job.company or "",
        str(application.resume_version_id) if application.resume_version_id else None,
        letter, email,
    )
    if _hash_snapshot(current_snapshot) != approval.payload_hash:
        return {
            "status": "halted",
            "error": "approval payload changed since review",
            "_summary": "This application changed after you reviewed it — please try again",
        }

    result = await deps.email_sender.send(
        EmailMessage(
            to_email=email.to_email or "", to_name=email.to_name,
            subject=email.subject, body=email.body, body_format=email.body_format,
        )
    )

    now = datetime.now(UTC)
    email.status = "sent"
    email.provider = result.provider
    email.provider_message_id = result.provider_message_id
    email.sent_at = now
    application.status = "applied"
    application.applied_at = now
    application.last_status_change_at = now
    await deps.session.flush()

    await audit(
        deps.session,
        actor_type="mana_ai",
        action="application.email_sent",
        on_behalf_of_user_id=deps.user_id,
        resource_type="application",
        resource_id=application.id,
        meta={"provider": result.provider, "application_email_id": str(email.id)},
    )

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="email_external_action",
        action_key="sent_application_email",
        summary=f"Application sent at {now.strftime('%-I:%M %p')}",
        entity_type="application",
        entity_id=application.id,
    )

    return {"status": "completed", "_summary": "Application sent"}
```

- [ ] **Step 2: extend `tests/domain/agents/test_nodes_approval.py`** — add:
```python
async def test_email_external_action_halts_when_not_approved():
    from unittest.mock import AsyncMock

    from app.domain.agents.nodes.email_external_action import email_external_action

    deps = AsyncMock()
    approval = AsyncMock(status="pending")
    deps.session.get = AsyncMock(return_value=approval)

    out = await email_external_action(
        {"approval_request_id": "11111111-1111-1111-1111-111111111111"}, deps=deps
    )
    assert out["status"] == "halted"
```

- [ ] **Step 3: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/agents/test_nodes_approval.py`
Expected: all PASS (5 tests).

```bash
git add backend/app/domain/agents/nodes/email_external_action.py backend/tests/domain/agents/test_nodes_approval.py
git commit -m "feat(agents): email_external_action -- assert approved + hash match, send, audit"
```

---

## Task 7: graph wiring + `respond` blocks

**Files:** Modify `backend/app/domain/agents/graph.py`, `backend/app/domain/agents/nodes/respond.py`, `backend/app/domain/agents/nodes/__init__.py`. Create `backend/tests/domain/agents/test_graph_approval.py`.

**Interfaces:**
- Consumes: the 3 new nodes (Tasks 4-6), `ApprovalActionBlock` (already exists unchanged, Phase 7a).
- Produces: `resume_tailoring → ... → email_draft → application_prep → human_approval → {email_external_action | halted}`, `email_external_action → respond`.

- [ ] **Step 1: `app/domain/agents/nodes/__init__.py`** — add the 3 new imports + `__all__` entries alphabetically:
```python
from app.domain.agents.nodes.application_prep import application_prep
from app.domain.agents.nodes.claim_validator import claim_validator
from app.domain.agents.nodes.cover_letter import cover_letter
from app.domain.agents.nodes.email_draft import email_draft
from app.domain.agents.nodes.email_external_action import email_external_action
from app.domain.agents.nodes.halted import halted
from app.domain.agents.nodes.human_approval import human_approval
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
    "application_prep",
    "claim_validator",
    "cover_letter",
    "email_draft",
    "email_external_action",
    "halted",
    "human_approval",
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

- [ ] **Step 2: `graph.py`** — add imports:
```python
from app.domain.agents.nodes.application_prep import application_prep
from app.domain.agents.nodes.email_external_action import email_external_action
from app.domain.agents.nodes.human_approval import human_approval
```
`AgentDeps` gains a field (insert after `svc: AgentService`):
```python
    email_sender: EmailSender
```
(add `from app.domain.email.sender import EmailSender` to the imports.)

In `build_graph`, the guard-wrapped node list gains `application_prep` and `email_external_action` (NOT `human_approval` — that one is registered separately, raw):
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
        ("application_prep", application_prep),
        ("email_external_action", email_external_action),
        ("respond", respond),
    ]:
```
Immediately after that loop and the existing `g.add_node("halted", partial(halted, deps=deps))` line, register `human_approval` RAW:
```python
    g.add_node("human_approval", partial(human_approval, deps=deps))
```

Add a routing function for the raw node, next to `_route_from_supervisor`:
```python
def _route_from_human_approval(state: ManaState) -> str:
    return state.get("_route", "halted")
```

Replace the existing `email_draft → respond` edge:
```python
    g.add_conditional_edges(
        "email_draft",
        _halt_or("respond"),
        {"respond": "respond", "halted": "halted"},
    )
```
with:
```python
    g.add_conditional_edges(
        "email_draft",
        _halt_or("application_prep"),
        {"application_prep": "application_prep", "halted": "halted"},
    )
    g.add_conditional_edges(
        "application_prep",
        _halt_or("human_approval"),
        {"human_approval": "human_approval", "halted": "halted"},
    )
    g.add_conditional_edges(
        "human_approval",
        _route_from_human_approval,
        {"email_external_action": "email_external_action", "halted": "halted"},
    )
    g.add_conditional_edges(
        "email_external_action",
        _halt_or("respond"),
        {"respond": "respond", "halted": "halted"},
    )
```

Refresh the module docstring's node/worker-node counts one more time: "thirteen nodes"/"eleven worker nodes" → "sixteen nodes"/"twelve worker nodes" (the 3 new nodes: `application_prep` and `email_external_action` are guard-wrapped workers; `human_approval` is raw like `supervisor`/`halted`, so "raw" nodes go from 2 to 3 — update whichever exact phrasing the current docstring uses to describe the raw-vs-worker split, matching its existing style).

- [ ] **Step 3: `respond.py`** — add a new branch, checked BEFORE the existing `email_draft_id` branch (an application that reached `application_prep` has `email_draft_id` set too, and the fuller/later outcome must win).

**Confirmed by tracing the full control flow (not left for the implementer to determine):** `respond` is reachable only via `email_external_action → respond` (a completed send) or via a `halted` short-circuit elsewhere — never while the graph is paused. `human_approval`'s first pass ends inside `interrupt()`; the astream generator stops there and `respond` never runs that turn. Task 8's `_drive()` helper detects the pause itself (via `snap.interrupts`) and returns without re-entering the graph. So `respond` only ever sees `state["status"] == "completed"` for a `prepare_application` run that reached this point — there is no live case where `respond` runs with `status == "awaiting_approval"`. Accordingly, this task adds exactly ONE new branch, not two — the "your application is ready, nothing sent until you approve" copy belongs to the SSE `approval` event / `GET /approvals/{id}` (both already deliver the pending-approval context on their own), not to a `respond` block that would never fire. `ApprovalActionBlock` stays unused by `respond.py` this phase (Phase 10b's frontend can still render it directly off the SSE `approval` event's `approval_id` without needing a response block to carry it).
```python
    blocks: list[BaseModel]
    if state.get("application_id") and state.get("status") == "completed":
        text = "Your application was sent — nice work!"
        blocks = [TextBlock(markdown=text)]
    elif state.get("email_draft_id"):
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
(the `elif not state.get("retrieved_jobs"):` line and everything below it is the existing code, unchanged — just one more `elif` added ahead of it in the chain.) No new import is needed in `respond.py` for this task — `ApprovalActionBlock` is not used here (see above).

- [ ] **Step 4: `tests/domain/agents/test_graph_approval.py`**
```python
from app.domain.agents.graph import _route_from_human_approval


def test_route_from_human_approval_reads_the_explicit_route():
    assert _route_from_human_approval({"_route": "email_external_action"}) == "email_external_action"


def test_route_from_human_approval_defaults_to_halted():
    assert _route_from_human_approval({}) == "halted"
```

- [ ] **Step 5: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run pytest -q tests/domain/agents/test_graph_approval.py tests/domain/agents/test_graph_tailor.py tests/domain/agents/test_graph_prepare_application.py`
Expected: all PASS.

```bash
git add backend/app/domain/agents/graph.py backend/app/domain/agents/nodes/respond.py backend/app/domain/agents/nodes/__init__.py backend/tests/domain/agents/test_graph_approval.py
git commit -m "feat(agents): wire application_prep -> human_approval -> email_external_action into the graph"
```

---

## Task 8: `run_agent`/`resume_agent` worker refactor (SUBAGENT REVIEW — high-risk, worker retry paths)

**Files:** Modify `backend/app/worker/tasks/agent.py`, `backend/app/worker/main.py`, `backend/app/domain/agents/service.py`.

**Interfaces:**
- Produces: `run_agent` (existing signature, same F3 retry discipline, refactored internals); `resume_agent(ctx, run_id, decision, note) -> dict`; `AgentService.mark_awaiting_approval(session_id)`, `AgentService.resume_run(user_id, session_id, *, decision, note) -> str`, `AgentService.RESUME_JOB = "resume_agent"`.

- [ ] **Step 1: `app/domain/agents/service.py`** — add `RESUME_JOB` next to `RUN_JOB`:
```python
    RUN_JOB = "run_agent"
    RESUME_JOB = "resume_agent"
```
Add two new methods (place them right after `stop_run`):
```python
    async def mark_awaiting_approval(self, session_id: uuid.UUID) -> None:
        """The run paused at a human_approval interrupt -- status only, no ended_at."""
        session = await self._session.get(AiSession, session_id)
        if session is None:
            raise NotFoundError("Session not found")
        session.status = "awaiting_approval"
        await self._session.flush()

    async def resume_run(
        self, user_id: uuid.UUID, session_id: uuid.UUID, *, decision: str, note: str | None
    ) -> str:
        session = await self.get_session(user_id, session_id)
        if session.status != "awaiting_approval" or not session.run_id:
            raise ValidationAppError("This session has no pending approval to resume.")
        run_id = session.run_id
        session.status = "running"
        await self._session.flush()
        await enqueue(
            self.RESUME_JOB, run_id, decision, note,
            _defer_by=1.0, _job_id=f"resume_agent:{run_id}",
        )
        return run_id
```

- [ ] **Step 2: `app/worker/tasks/agent.py`** — extract the shared drive logic and add `resume_agent`. Read the CURRENT file in full first (it has not changed since Phase 7a; the version this brief was written against is reproduced in this plan's context above) — then restructure it to this shape, preserving every existing comment/docstring that still applies:

```python
"""``run_agent``/``resume_agent`` -- the ARQ worker tasks that drive a Mana
Career LangGraph run.

``run_agent`` starts a fresh run; ``resume_agent`` resumes one paused at a
``human_approval`` interrupt (Command(resume=...) instead of a fresh init --
see the Phase 10a spec R5/R6). Both share ``_drive()``, which streams the
compiled graph with ``stream_mode="updates"``, persists every StepEvent the
guard emits and republishes it (plus response blocks) to the run's SSE
channel, then either finalizes the session (the graph reached a terminal
state) or marks it ``awaiting_approval`` (the graph paused at a new
interrupt) by reading ``graph.aget_state(...).interrupts``. The
``except``/``finally`` block in each entry point follows the repo's F3
retry discipline: transient tries re-raise untouched; the terminal try
finalizes the session as ``error``, publishes a generic failure, and
records a dead-letter entry.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from langgraph.types import Command
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.domain.agents.checkpointer import get_checkpointer
from app.domain.agents.graph import AgentDeps, build_graph
from app.domain.agents.search.factory import get_search_provider
from app.domain.agents.service import AgentService
from app.domain.agents.state import ManaState
from app.domain.email.factory import get_email_sender
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.llm.factory import get_llm_provider
from app.models.ai import AiSession
from app.worker.dead_letter import record_failure
from app.worker.tasks.resume import MAX_TRIES

__all__ = ["run_agent", "resume_agent"]

log = get_logger("worker.run_agent")


@contextlib.asynccontextmanager
async def _session_for() -> AsyncIterator[AsyncSession]:
    """Session seam for the résumé pipeline.

    Production opens a fresh ``AsyncSessionLocal`` (its own transaction, closed
    on exit). The DB-backed test monkeypatches this to an async-CM that yields
    the shared rolled-back ``db_session`` without closing it, so every
    ``session.commit()`` below just releases/re-opens that session's SAVEPOINT
    (``join_transaction_mode="create_savepoint"``) and the fixture's outer
    ``trans.rollback()`` still discards the whole test's writes.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def _drive(
    *, session: AsyncSession, s: AiSession, run_id: str, graph_input: Any,
    settings: Any, redis: Redis, publish: Any,
) -> dict[str, Any]:
    svc = AgentService(session, settings=settings)
    deps = AgentDeps(
        session=session,
        llm=get_llm_provider(settings),
        embeddings=get_embeddings_provider(settings),
        search=get_search_provider(settings),
        checkpointer=await get_checkpointer(settings),
        publish=publish,
        svc=svc,
        email_sender=get_email_sender(settings),
        user_id=s.user_id,
        run_id=run_id,
        session_id=s.id,
    )
    graph = build_graph(deps)
    gcfg = {"configurable": {"thread_id": run_id}}
    await publish({"event": "open", "run_id": run_id})
    async for update in graph.astream(graph_input, config=gcfg, stream_mode="updates"):
        for _node_name, partial_state in update.items():
            if not isinstance(partial_state, dict):
                continue
            for ev in partial_state.get("step_log", []):
                await svc._write_step(session_id=s.id, run_id=run_id, step=ev)
                await publish(
                    {
                        "event": "step",
                        "node": ev["node"],
                        "status": ev["status"],
                        "summary": ev["summary"],
                    }
                )
            for b in partial_state.get("blocks", []):
                await publish({"event": "block", "block": b})

    snap = await graph.aget_state(gcfg)
    if snap.interrupts:
        await svc.mark_awaiting_approval(s.id)
        await session.commit()
        interrupt_value = snap.interrupts[0].value
        approval_id = (
            interrupt_value.get("approval_id")
            if isinstance(interrupt_value, dict)
            else None
        )
        await publish({"event": "approval", "approval_id": approval_id})
        await publish({"event": "done", "status": "awaiting_approval", "totals": {}})
        return {"run_id": run_id, "status": "awaiting_approval"}

    final = snap.values
    fstatus = final.get("status", "completed")
    totals = {
        "steps": final.get("budget", {}).get("steps_taken", 0),
        "cost_usd": final.get("budget", {}).get("cost_usd", 0.0),
        "llm_calls": final.get("budget", {}).get("llm_calls_made", 0),
    }
    await svc.finalize(
        session_id=s.id, status=fstatus, totals=totals, error=final.get("error")
    )
    await session.commit()
    await publish({"event": "done", "status": fstatus, "totals": totals})
    return {"run_id": run_id, "status": fstatus}


async def _run_or_resume(
    ctx: dict[str, Any], run_id: str, graph_input_factory: Any,
) -> dict[str, Any]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    channel = f"sse:ai:{run_id}"

    async def publish(event: dict[str, Any]) -> None:
        await redis.publish(channel, json.dumps(event, default=str))

    async with _session_for() as session:
        s = (
            await session.execute(select(AiSession).where(AiSession.run_id == run_id))
        ).scalar_one_or_none()
        if s is None:
            await record_failure(
                "run_agent", args=(run_id,), kwargs={},
                error=RuntimeError(f"run {run_id} not found"),
            )
            return {"run_id": run_id, "status": "missing"}
        try:
            graph_input = graph_input_factory(s)
            return await _drive(
                session=session, s=s, run_id=run_id, graph_input=graph_input,
                settings=settings, redis=redis, publish=publish,
            )
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise
            s2 = (
                await session.execute(select(AiSession).where(AiSession.run_id == run_id))
            ).scalar_one_or_none()
            if s2 is not None:
                await AgentService(session).finalize(
                    session_id=s2.id, status="error", totals={}, error=str(exc)[:500]
                )
                await session.commit()
            await publish({"event": "error", "message": "The run failed."})
            await publish({"event": "done", "status": "error", "totals": {}})
            await record_failure("run_agent", args=(run_id,), kwargs={}, error=exc)
            raise
        finally:
            await redis.aclose()


async def run_agent(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    def _fresh_init(s: AiSession) -> ManaState:
        cfg = s.run_config or {}
        return {
            "run_id": run_id,
            "session_id": str(s.id),
            "user_id": str(s.user_id),
            "goal": cfg.get("goal", "understand_job"),
            "inputs": cfg.get("inputs", {}),
            "budget": s.budget,  # type: ignore[typeddict-item]  # JSONB dict -> Budget
            "tool_cache": {},
            "step_log": [],
            "stop_requested": bool(cfg.get("stop")),
            "status": "running",
        }

    return await _run_or_resume(ctx, run_id, _fresh_init)


async def resume_agent(
    ctx: dict[str, Any], run_id: str, decision: str, note: str | None
) -> dict[str, Any]:
    def _resume_command(_s: AiSession) -> Command:
        return Command(resume={"decision": decision, "note": note})

    return await _run_or_resume(ctx, run_id, _resume_command)
```

**Empirically verified, not just traced from docs:** the `isinstance(partial_state, dict)` guard and the `snap.interrupts` pause-detection above were confirmed by actually running a minimal two-node interrupting graph against this project's installed `langgraph==1.2.11` while writing this plan. The exact observed `astream(..., stream_mode="updates")` sequence for a node that calls `interrupt(payload)`:
```
UPDATE: {'a': {'x': 1}}                                    # a normal node's update -- a dict, .get() works
UPDATE: {'__interrupt__': (Interrupt(value=payload, id='...'),)}   # the pause -- value is a TUPLE, not a dict
```
followed by `snap.interrupts == (Interrupt(value=payload, id='...'),)`, `snap.next == ('b',)` (the paused node). Resuming via `compiled.astream(Command(resume={...}), config=same_cfg, stream_mode="updates")` on the SAME `thread_id` yields `{'b': {'x': ...}}` with `interrupt()` inside the node returning exactly the `resume` dict, and `snap.interrupts` is `()` again once the run reaches a real terminal state. This is exactly the shape `_drive()` above is written against.

Still confirm the refactor's non-interrupt behavior (F3 retry sequence, SSE event shapes, the `_session_for` docstring) matches the CURRENT `app/worker/tasks/agent.py` on disk (Task 7's commit is the branch tip) before committing — this plan's reproduction of that "before" state is accurate as of when it was written, but the file is real, active code and deserves a direct read, not blind trust in a plan.

- [ ] **Step 2: `app/worker/main.py`** — add the import and registration:
```python
from app.worker.tasks import (
    build_profile,
    extract_resume,
    ingest_job,
    parse_resume,
    ping,
    resume_agent,
    run_agent,
    score_match,
)
```
```python
    functions: ClassVar[list[Any]] = [
        ping,
        parse_resume,
        extract_resume,
        build_profile,
        ingest_job,
        score_match,
        run_agent,
        resume_agent,
    ]
```
`app/worker/tasks/__init__.py` (confirmed current content) re-exports explicitly — add `resume_agent` to both the import and `__all__`:
```python
from app.worker.tasks.agent import resume_agent, run_agent
```
```python
__all__ = [
    "build_profile",
    "extract_resume",
    "ingest_job",
    "parse_resume",
    "ping",
    "resume_agent",
    "run_agent",
    "score_match",
]
```

- [ ] **Step 3: gate**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: all clean. (No new pure tests this task — Task 8's own correctness is proven by Task 11's DB-gated integration test; do not invent a shallow pure test that mocks everything and asserts nothing meaningful.)

```bash
git add backend/app/worker/tasks/agent.py backend/app/worker/main.py backend/app/domain/agents/service.py
git commit -m "refactor(worker): extract _drive(); resume_agent resumes a paused run via Command"
```

---

## Task 9: `/applications` API

**Files:** Create `backend/app/api/v1/schemas/applications.py`, `backend/app/api/v1/applications.py`, `backend/tests/api/test_applications.py`. Modify `backend/app/api/v1/router.py`.

**Interfaces:**
- Produces: `POST /applications` → 202 `RunRefOut`; `GET /applications/{id}` → `ApplicationOut`.

- [ ] **Step 1: `app/api/v1/schemas/applications.py`**
```python
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ApplicationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    resume_version_id: uuid.UUID | None
    cover_letter_id: uuid.UUID | None
    application_email_id: uuid.UUID | None
    status: str
    match_score: Decimal | None
    source: str
    applied_at: dt.datetime | None
    last_status_change_at: dt.datetime
    created_at: dt.datetime
    updated_at: dt.datetime
```

- [ ] **Step 2: `app/api/v1/applications.py`**
```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.ai import RunRefOut
from app.api.v1.schemas.applications import ApplicationCreateIn, ApplicationOut
from app.core.errors import NotFoundError
from app.domain.agents.service import AgentService
from app.models.application import Application

router = APIRouter(prefix="/applications", tags=["applications"])


def _application_out(a: Application) -> ApplicationOut:
    return ApplicationOut(
        id=a.id, job_id=a.job_id, resume_version_id=a.resume_version_id,
        cover_letter_id=a.cover_letter_id, application_email_id=a.application_email_id,
        status=a.status, match_score=a.match_score, source=a.source,
        applied_at=a.applied_at, last_status_change_at=a.last_status_change_at,
        created_at=a.created_at, updated_at=a.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_application(
    body: ApplicationCreateIn, db: DbDep, user: CurrentUser
) -> RunRefOut:
    session = await AgentService(db).create_session(user.id, kind="agent_run")
    run_id = await AgentService(db).start_run(
        user.id, session.id, goal="prepare_application",
        inputs={"job_id": str(body.job_id)},
    )
    await db.commit()
    return RunRefOut(run_id=run_id, session_id=str(session.id))


@router.get("/{application_id}")
async def get_application(
    application_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ApplicationOut:
    row = (
        await db.execute(
            select(Application).where(
                Application.id == application_id, Application.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(detail="Application not found")
    return _application_out(row)
```

- [ ] **Step 3: `app/api/v1/router.py`** — this task adds ONLY `applications` (Task 10 adds `approvals` in its own, later edit to these same two lines — never both in one task, since Task 10's module doesn't exist yet when this task runs). Current file:
```python
from fastapi import APIRouter

from app.api.v1 import ai, auth, eval, health, jobs, matches, profile, resumes, skill_gaps

api_router = APIRouter()
api_router.include_router(ai.router)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(eval.router)
api_router.include_router(jobs.router)
api_router.include_router(matches.router)
api_router.include_router(profile.router)
api_router.include_router(resumes.router)
api_router.include_router(skill_gaps.router)
```
Change the import line to:
```python
from app.api.v1 import (
    ai,
    applications,
    auth,
    eval,
    health,
    jobs,
    matches,
    profile,
    resumes,
    skill_gaps,
)
```
and add, anywhere among the existing `include_router` calls (alphabetical order is this file's existing style but not load-bearing — match it):
```python
api_router.include_router(applications.router)
```

- [ ] **Step 4: `tests/api/test_applications.py`** (DB-gated, CI-only). This mirrors `tests/api/test_resumes_versions.py`'s (Phase 8a) exact, confirmed convention: a local `_auth(client, email)` helper does a real register+login HTTP round trip and returns a bearer-token header dict — there is no `auth_headers` fixture in this codebase.
```python
"""POST /applications + GET /applications/{id} -- DB integration, CI-deferred."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.job import Job
from app.models.user import User


async def _auth(client, email):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed_job(db_session) -> Job:
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    return j


async def test_get_application_not_found_for_another_user(client, db_session):
    h = await _auth(client, "app-owner@x.com")
    r = await client.get(f"/api/v1/applications/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404


async def test_create_application_returns_202_run_ref(client, db_session):
    h = await _auth(client, "app-create@x.com")
    job = await _seed_job(db_session)
    r = await client.post("/api/v1/applications", headers=h, json={"job_id": str(job.id)})
    assert r.status_code == 202
    body = r.json()
    assert body["run_id"]
    assert body["session_id"]


async def test_get_application_after_direct_insert(client, db_session):
    from app.models.application import Application

    h = await _auth(client, "app-read@x.com")
    user = (
        await db_session.execute(select(User).where(User.email == "app-read@x.com"))
    ).scalar_one()
    job = await _seed_job(db_session)
    application = Application(user_id=user.id, job_id=job.id)
    db_session.add(application)
    await db_session.flush()

    r = await client.get(f"/api/v1/applications/{application.id}", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "preparing"
```

- [ ] **Step 5: gate**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: all clean (DB-gated test collects but is not run).

```bash
git add backend/app/api/v1/schemas/applications.py backend/app/api/v1/applications.py backend/app/api/v1/router.py backend/tests/api/test_applications.py
git commit -m "feat(applications): POST /applications + GET /applications/{id}"
```

---

## Task 10: `/approvals` API

**Files:** Create `backend/app/api/v1/schemas/approvals.py`, `backend/app/api/v1/approvals.py`, `backend/tests/api/test_approvals.py`. Modify `backend/app/api/v1/router.py`.

**Interfaces:**
- Produces: `GET /approvals?status=pending`, `GET /approvals/{id}`, `POST /approvals/{id}`.

- [ ] **Step 1: `app/api/v1/schemas/approvals.py`**
```python
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApprovalDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    note: str | None = None


class ApprovalRequestOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    action_type: str
    payload_snapshot: dict[str, Any]
    status: str
    decided_at: dt.datetime | None
    decision_note: str | None
    created_at: dt.datetime


class ApprovalRequestListOut(BaseModel):
    items: list[ApprovalRequestOut]
```

- [ ] **Step 2: `app/api/v1/approvals.py`**
```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.approvals import (
    ApprovalDecisionIn,
    ApprovalRequestListOut,
    ApprovalRequestOut,
)
from app.core.errors import ConflictError, NotFoundError
from app.domain.agents.service import AgentService
from app.models.application import ApprovalRequest

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _approval_out(a: ApprovalRequest) -> ApprovalRequestOut:
    return ApprovalRequestOut(
        id=a.id, application_id=a.application_id, action_type=a.action_type,
        payload_snapshot=dict(a.payload_snapshot), status=a.status,
        decided_at=a.decided_at, decision_note=a.decision_note, created_at=a.created_at,
    )


async def _get_owned(db, user_id: uuid.UUID, approval_id: uuid.UUID) -> ApprovalRequest:
    row = (
        await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == approval_id, ApprovalRequest.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(detail="Approval not found")
    return row


@router.get("")
async def list_approvals(
    db: DbDep, user: CurrentUser, status: str | None = None
) -> ApprovalRequestListOut:
    # Named `status`, shadowing the `fastapi.status` module import within this
    # function's local scope only -- this function never references
    # `status.HTTP_*` itself (the POST route below does, in its own separate
    # scope), so there is no actual conflict and no alias is needed. FastAPI
    # maps a plain parameter name straight to the same-named query key, so
    # this already serves `GET /approvals?status=pending` correctly.
    stmt = select(ApprovalRequest).where(ApprovalRequest.user_id == user.id)
    if status is not None:
        stmt = stmt.where(ApprovalRequest.status == status)
    rows = (await db.execute(stmt.order_by(ApprovalRequest.created_at.desc()))).scalars().all()
    return ApprovalRequestListOut(items=[_approval_out(r) for r in rows])


@router.get("/{approval_id}")
async def get_approval(
    approval_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ApprovalRequestOut:
    return _approval_out(await _get_owned(db, user.id, approval_id))


@router.post("/{approval_id}", status_code=status.HTTP_202_ACCEPTED)
async def decide_approval(
    approval_id: uuid.UUID, body: ApprovalDecisionIn, db: DbDep, user: CurrentUser
) -> None:
    approval = await _get_owned(db, user.id, approval_id)
    if approval.status != "pending":
        raise ConflictError("This approval has already been decided.")

    approval.status = "approved" if body.decision == "approve" else "rejected"
    approval.decided_by = user.id
    approval.decided_at = datetime.now(UTC)
    approval.decision_note = body.note
    await db.flush()

    await AgentService(db).resume_run(
        user.id, approval.ai_session_id, decision=body.decision, note=body.note
    )
    await db.commit()
```

- [ ] **Step 3: `app/api/v1/router.py`** — finish the edit Task 9 started: add `approvals` to the import (already present if Task 9 added the combined tuple — otherwise add it now) and:
```python
api_router.include_router(approvals.router)
```

- [ ] **Step 4: `tests/api/test_approvals.py`** (DB-gated, CI-only) — same verified `_auth(client, email)` convention as Task 9's `test_applications.py` (no `auth_headers` fixture exists in this codebase):
```python
"""GET/POST /approvals -- DB integration, CI-deferred."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.application import Application, ApprovalRequest
from app.models.job import Job
from app.models.user import User


async def _auth(client, email):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed_pending_approval(db_session, email):
    user = User(email=email, password_hash="x", full_name="U")
    db_session.add(user)
    await db_session.flush()
    job = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(job)
    await db_session.flush()
    application = Application(user_id=user.id, job_id=job.id, status="awaiting_approval")
    db_session.add(application)
    await db_session.flush()
    approval = ApprovalRequest(
        user_id=user.id, application_id=application.id, ai_session_id=application.id,
        run_id=f"run-{application.id.hex}", payload_hash="a" * 64,
    )
    db_session.add(approval)
    await db_session.flush()
    return user, application, approval


async def test_get_approval_not_found_for_another_user(client, db_session):
    h = await _auth(client, "approval-owner@x.com")
    r = await client.get(f"/api/v1/approvals/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404


async def test_list_approvals_filters_by_status(client, db_session):
    h = await _auth(client, "approval-list@x.com")
    user = (
        await db_session.execute(select(User).where(User.email == "approval-list@x.com"))
    ).scalar_one()
    _u2, _app, approval = await _seed_pending_approval(db_session, "approval-list-owner@x.com")
    # the seeded approval belongs to a different user -- it must not appear
    r = await client.get("/api/v1/approvals?status=pending", headers=h)
    assert r.status_code == 200
    assert approval.id not in {uuid.UUID(item["id"]) for item in r.json()["items"]}


async def test_decide_approval_rejects_a_second_decision(client, db_session, monkeypatch):
    # AgentService.resume_run enqueues a real ARQ job over Redis; this test
    # only exercises the ApprovalRequest state machine and the route's own
    # ownership + idempotency checks, so patch the enqueue call to a no-op --
    # find and reuse whatever monkeypatch target the codebase's own
    # AgentService/enqueue tests already use for this (e.g. patching
    # `app.core.queue.enqueue` or `app.domain.agents.service.enqueue`) rather
    # than guessing a new one here.
    monkeypatch.setattr("app.domain.agents.service.enqueue", lambda *a, **k: None)

    h = await _auth(client, "approval-decide@x.com")
    user = (
        await db_session.execute(select(User).where(User.email == "approval-decide@x.com"))
    ).scalar_one()
    job = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(job)
    await db_session.flush()
    application = Application(user_id=user.id, job_id=job.id, status="awaiting_approval")
    db_session.add(application)
    await db_session.flush()
    from app.domain.agents.service import AgentService

    session = await AgentService(db_session).create_session(user.id, kind="agent_run")
    await AgentService(db_session).start_run(
        user.id, session.id, goal="prepare_application", inputs={"job_id": str(job.id)}
    )
    await db_session.refresh(session)
    session.status = "awaiting_approval"
    approval = ApprovalRequest(
        user_id=user.id, application_id=application.id, ai_session_id=session.id,
        run_id=session.run_id, payload_hash="a" * 64,
    )
    db_session.add(approval)
    await db_session.flush()

    r1 = await client.post(
        f"/api/v1/approvals/{approval.id}", headers=h, json={"decision": "approve"}
    )
    assert r1.status_code == 202

    r2 = await client.post(
        f"/api/v1/approvals/{approval.id}", headers=h, json={"decision": "approve"}
    )
    assert r2.status_code == 409
```
`app.domain.agents.service.enqueue` is the correct patch target (confirmed): `service.py` does `from app.core.queue import enqueue`, which binds the name into that module's own namespace — `monkeypatch.setattr` must target where a name is *used*, not where it's defined, for a `from X import Y` style import.

- [ ] **Step 5: gate**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: all clean (DB-gated tests collect but are not run).

```bash
git add backend/app/api/v1/schemas/approvals.py backend/app/api/v1/approvals.py backend/app/api/v1/router.py backend/tests/api/test_approvals.py
git commit -m "feat(applications): GET/POST /approvals -- approve/reject resumes the paused run"
```

---

## Task 11: full-chain interrupt/resume worker integration test (SUBAGENT REVIEW — the critical test of this phase)

**Files:** Create `backend/tests/worker/test_resume_agent.py`.

**Interfaces:**
- Consumes: everything from Tasks 1-8. Writes no new production code.

This is the single most important test in Phase 10a: it must prove the graph genuinely PAUSES at `human_approval` (worker task returns, session status is `awaiting_approval`, nothing sent), and that a SEPARATE later call to `resume_agent` with an approve decision genuinely RESUMES the same thread, reaches `email_external_action`, sends via the console sender, and reaches `completed` — using the real `run_agent`/`resume_agent`/`AgentService.resume_run` machinery, not a hand-rolled substitute.

- [ ] **Step 1: read `tests/worker/test_prepare_application_task.py`** (Phase 9) in full first — mirror its `_ctx`/`_fake_redis_cls`/`_seed`-style helpers exactly (byte-identical copies, per this codebase's established worker-test convention).

- [ ] **Step 2: `tests/worker/test_resume_agent.py`**
```python
"""run_agent pausing at human_approval, resume_agent resuming it -- DB
integration, CI-deferred. The critical test of Phase 10a."""
from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.agents.service import AgentService
from app.models.ai import AiSession
from app.models.application import Application, ApplicationEmail, ApprovalRequest
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.worker.tasks.agent import resume_agent, run_agent


@contextlib.asynccontextmanager
async def _ctx(session):
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


async def test_run_agent_pauses_then_resume_agent_sends(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr("app.worker.tasks.agent._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis))

    u, resume, job = await _seed(db_session, "resume-agent@x.com")
    svc = AgentService(db_session)
    sess = await svc.create_session(u.id, kind="agent_run")
    run_id = await svc.start_run(
        u.id, sess.id, goal="prepare_application",
        inputs={"job_id": str(job.id), "resume_id": str(resume.id)},
    )

    # --- first invocation: runs to the interrupt and STOPS, nothing sent ---
    out = await run_agent({}, run_id)
    assert out == {"run_id": run_id, "status": "awaiting_approval"}

    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "awaiting_approval"
    assert session_row.ended_at is None  # not finalized -- still paused, not done

    application = (
        await db_session.execute(select(Application).where(Application.job_id == job.id))
    ).scalar_one()
    assert application.status == "awaiting_approval"

    email = (
        await db_session.execute(
            select(ApplicationEmail).where(ApplicationEmail.job_id == job.id)
        )
    ).scalar_one()
    assert email.status == "draft"  # not sent yet

    approval = (
        await db_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.application_id == application.id)
        )
    ).scalar_one()
    assert approval.status == "pending"

    # --- decide + resume: mirrors what POST /approvals/{id} does ---
    approval.status = "approved"
    approval.decided_by = u.id
    approval.decided_at = datetime.now(UTC)
    await db_session.flush()

    out2 = await resume_agent({}, run_id, "approve", None)
    assert out2 == {"run_id": run_id, "status": "completed"}

    await db_session.refresh(session_row)
    assert session_row.status == "completed"
    assert session_row.ended_at is not None

    await db_session.refresh(application)
    assert application.status == "applied"
    assert application.applied_at is not None

    await db_session.refresh(email)
    assert email.status == "sent"
    assert email.provider == "console"
    assert email.provider_message_id and email.provider_message_id.startswith("console-")
    assert email.sent_at is not None


async def test_run_agent_pauses_then_resume_agent_rejects(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr("app.worker.tasks.agent._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis))

    u, resume, job = await _seed(db_session, "resume-agent-reject@x.com")
    svc = AgentService(db_session)
    sess = await svc.create_session(u.id, kind="agent_run")
    run_id = await svc.start_run(
        u.id, sess.id, goal="prepare_application",
        inputs={"job_id": str(job.id), "resume_id": str(resume.id)},
    )
    await run_agent({}, run_id)

    application = (
        await db_session.execute(select(Application).where(Application.job_id == job.id))
    ).scalar_one()
    approval = (
        await db_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.application_id == application.id)
        )
    ).scalar_one()
    approval.status = "rejected"
    approval.decided_by = u.id
    approval.decided_at = datetime.now(UTC)
    await db_session.flush()

    out = await resume_agent({}, run_id, "reject", "not a fit")
    assert out == {"run_id": run_id, "status": "rejected"}

    email = (
        await db_session.execute(
            select(ApplicationEmail).where(ApplicationEmail.job_id == job.id)
        )
    ).scalar_one()
    assert email.status == "draft"  # never sent -- reject is terminal (R8)
```

- [ ] **Step 3: gate**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: all clean. Do NOT run this test locally (DB-gated).

```bash
git add backend/tests/worker/test_resume_agent.py
git commit -m "test(agents): interrupt-then-resume across two worker invocations -- approve sends, reject doesn't (DB-gated)"
```

---

## Task 12: verification + whole-branch review + completion report + squash + push + CI

Controller-only, no subagent. Mirror the Phase 8a/8b/9 closeout exactly:
1. Full local gate on the branch tip: ruff, mypy, lint-imports (`3 kept, 0 broken`), `pytest -q --collect-only` (error-free), `alembic heads` (single head `0013_applications_approvals`).
2. Run every pure test suite added/modified across all 11 tasks (skip every DB-gated file: `test_application_approval_models.py`, `test_resume_agent.py`, `test_applications.py`, `test_approvals.py`).
3. Whole-branch review (inline, except the two subagent-reviewed tasks already covered — Task 3's migration and Task 11's integration test): read the full commit range diff, scan for TODO/FIXME/stubs, trace type consistency end to end (`ManaState.status`/`approval_request_id` through every node that reads or writes them; `AgentDeps.email_sender` through `graph.py` → `email_external_action`; the `_build_snapshot`/`_hash_snapshot` functions imported identically by both `application_prep.py` and `email_external_action.py`, never duplicated). Also confirm Task 7's `respond.py` reachability question (the `awaiting_approval` branch) was actually resolved one way or the other, not left ambiguous.
4. Write the completion report into this plan file — same structure as every prior phase's (what changed, why, files, how to test, regression check with directly-verified baseline counts — do not guess a baseline number from partial subagent-report snippets; check out the branch's fork-point commit in an isolated worktree and run the count directly, the way Phase 9's closeout corrected its own first guess).
5. Squash to `main` (fast-forward if `main` is unmoved and the task commits are already clean — check first — else reconstruct via file-group `git checkout <tip> -- <paths>` + commit).
6. Push, watch CI. The `backend` job now exercises real interrupt/resume machinery for the first time — watch specifically for anything resembling the SSE/ASGITransport-style hang class of failure (per the standing memory note) even though this phase's SSE changes are all on the worker/publish side, not the HTTP relay; also watch for an Alembic partial-unique-index syntax failure specifically (Task 3's `postgresql_where` usage was verified against a live precedent but never executed against a real Postgres in this sandbox).
7. `finishing-a-development-branch`: delete the branch + `.superpowers/sdd/2026-09-05-phase-10a-human-approval-backend/`.
