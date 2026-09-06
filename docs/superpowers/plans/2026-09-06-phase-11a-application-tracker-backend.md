# Phase 11a — Application tracker (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The rest of the `/applications` resource the Kanban tracker needs — list, status change (with an `application_events` + `audit_logs` trail), notes, a merged timeline, soft-delete, and `POST /applications` gaining `intent=save`.

**Architecture:** New `application_events` table (migration `0014`). New `app/domain/applications/service.py` (`ApplicationService`). The Phase 10a `app/api/v1/applications.py` grows from 2 routes to 7.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-11a-application-tracker-backend.md` — read first (7 rulings R1-R7).

## Global Constraints

- Backend-only. Phase 11b is the Kanban/detail UI.
- No local Postgres/Redis. Local gates: `"$UV" run ruff check .` / `"$UV" run mypy app` / `"$UV" run lint-imports` (stays `3 kept, 0 broken`) / `"$UV" run pytest -q --collect-only` (error-free) + named pure suites. `$UV` = `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`. DB-gated tests run only in CI.
- Alembic chain `…→0013_applications_approvals→0014_application_events`, single head. Mirror `0013_applications_approvals.py`'s style.
- `mypy` strict. Every def fully annotated.
- `ApplicationService` is a `domain` leaf — imports `app.core.*` / `app.models.*` only, never `api`/`worker`/sibling domains. Reuse `app.core.audit.audit`.
- `application_events` is append-only: **only `created_at`** (plain column) + its own `occurred_at`, no `TimestampMixin`, no `updated_at` trigger (mirrors `audit_logs`).
- User-settable status subset (R3): `saved, applied, interview, offer, rejected, withdrawn` — NOT `preparing`/`awaiting_approval`.

---

## Task 1: `application_events` table + model (migration `0014`) — SUBAGENT REVIEW

**Files:** Create `backend/app/models/application_event.py`, `backend/alembic/versions/0014_application_events.py`, `backend/tests/models/test_application_event_model.py`. Modify `backend/app/models/__init__.py`.

**Interfaces:**
- Produces: `ApplicationEvent` (table `application_events`); single alembic head `0014_application_events`.

- [ ] **Step 1: `app/models/application_event.py`**
```python
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    __table_args__ = (
        CheckConstraint(
            "kind in ('status_change','note','interview_scheduled','ai_action','email_sent')",
            name="application_events_kind_valid",
        ),
        Index("ix_application_events_app", "application_id", text("occurred_at DESC")),
        Index("ix_application_events_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    body: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[dt.datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
```

- [ ] **Step 2: `app/models/__init__.py`** — insert alphabetically (after `application`):
```python
from app.models import application as application
from app.models import application_event as application_event
from app.models import audit as audit
```

- [ ] **Step 3: `alembic/versions/0014_application_events.py`** — mirrors `0013_applications_approvals.py`'s exact style (`_TS` / `_NOW` module locals, `pg.UUID` / `pg.JSONB`, inline `sa.CheckConstraint`). **No `set_updated_at` trigger** — append-only, `created_at` only, exactly like `0002_audit_logs.py`.
```python
"""application_events (append-only)

Revision ID: 0014_application_events
Revises: 0013_applications_approvals
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0014_application_events"
down_revision = "0013_applications_approvals"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "application_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("application_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20)),
        sa.Column("body", sa.Text),
        sa.Column("meta", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "kind in ('status_change','note','interview_scheduled','ai_action','email_sent')",
            name="application_events_kind_valid",
        ),
    )
    op.create_index("ix_application_events_app", "application_events",
                    ["application_id", sa.text("occurred_at DESC")])
    op.create_index("ix_application_events_user", "application_events", ["user_id"])


def downgrade() -> None:
    op.drop_table("application_events")
```

- [ ] **Step 4: `tests/models/test_application_event_model.py`** (DB-gated)
```python
"""ApplicationEvent model round-trip -- DB integration, CI-deferred."""
from __future__ import annotations

from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.job import Job
from app.models.user import User


async def test_application_event_round_trip(db_session):
    u = User(email="app-events@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    app_row = Application(user_id=u.id, job_id=j.id, status="saved", source="user")
    db_session.add(app_row)
    await db_session.flush()

    ev = ApplicationEvent(
        application_id=app_row.id, user_id=u.id, kind="status_change",
        from_status=None, to_status="saved",
    )
    db_session.add(ev)
    await db_session.flush()
    await db_session.refresh(ev)  # pull server defaults (meta, occurred_at, created_at)
    assert ev.meta == {}
    assert ev.occurred_at is not None
    assert ev.created_at is not None
```

- [ ] **Step 5: gate + verify migration**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only && "$UV" run alembic heads`
Expected: `lint-imports` `3 kept, 0 broken`; collection error-free; `alembic heads` → `0014_application_events (head)`. Do NOT run the DB test locally.

```bash
git add backend/app/models/application_event.py backend/app/models/__init__.py backend/alembic/versions/0014_application_events.py backend/tests/models/test_application_event_model.py
git commit -m "feat(applications): application_events table (migration 0014)"
```

---

## Task 2: `ApplicationService` — list / get / patch / add_note / soft_delete

**Files:** Create `backend/app/domain/applications/__init__.py`, `backend/app/domain/applications/service.py`, `backend/tests/domain/applications/__init__.py`, `backend/tests/domain/applications/test_application_service.py` (DB-gated).

**Interfaces:**
- Consumes: `Application`, `ApplicationEvent` (Task 1), `app.core.audit.audit`.
- Produces: `ApplicationService(session)` with `list_(user_id, *, status=None, sort="recent", limit=100, offset=0) -> tuple[list[Application], int]`, `get(user_id, application_id) -> Application`, `patch(user_id, application_id, *, status=None, notes=None) -> Application`, `add_note(user_id, application_id, body) -> ApplicationEvent`, `soft_delete(user_id, application_id) -> None`. (`timeline` is Task 3.)

- [ ] **Step 1: `app/domain/applications/__init__.py`** — empty.

- [ ] **Step 2: `app/domain/applications/service.py`**
```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.errors import NotFoundError, ValidationAppError
from app.models.application import Application
from app.models.application_event import ApplicationEvent

_USER_SETTABLE = {"saved", "applied", "interview", "offer", "rejected", "withdrawn"}

_PIPELINE_RANK = case(
    {
        "saved": 0, "preparing": 1, "awaiting_approval": 2, "applied": 3,
        "interview": 4, "offer": 5, "rejected": 6, "withdrawn": 7,
    },
    value=Application.status,
    else_=99,
)


class ApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
        sort: str = "recent",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Application], int]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        where = [Application.user_id == user_id, Application.deleted_at.is_(None)]
        if status is not None:
            where.append(Application.status == status)

        total = (
            await self._session.execute(
                select(func.count()).select_from(Application).where(*where)
            )
        ).scalar_one()

        stmt = select(Application).where(*where)
        if sort == "status":
            stmt = stmt.order_by(_PIPELINE_RANK, Application.updated_at.desc())
        else:
            stmt = stmt.order_by(Application.updated_at.desc())
        rows = (
            await self._session.execute(stmt.limit(limit).offset(offset))
        ).scalars().all()
        return list(rows), int(total)

    async def get(self, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
        row = (
            await self._session.execute(
                select(Application).where(
                    Application.id == application_id,
                    Application.user_id == user_id,
                    Application.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError(detail="Application not found")
        return row

    async def patch(
        self,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
        *,
        status: str | None = None,
        notes: str | None = None,
    ) -> Application:
        app_row = await self.get(user_id, application_id)
        now = datetime.now(UTC)

        if status is not None and status != app_row.status:
            if status not in _USER_SETTABLE:
                raise ValidationAppError(f"Can't set status to {status!r}.")
            from_status = app_row.status
            app_row.status = status
            app_row.last_status_change_at = now
            if status == "applied" and app_row.applied_at is None:
                app_row.applied_at = now
            self._session.add(
                ApplicationEvent(
                    application_id=app_row.id, user_id=user_id, kind="status_change",
                    from_status=from_status, to_status=status,
                )
            )
            await audit(
                self._session,
                actor_type="user",
                action="application.status_change",
                actor_user_id=user_id,
                resource_type="application",
                resource_id=app_row.id,
                meta={"from": from_status, "to": status},
            )

        if notes is not None:
            app_row.notes = notes  # notes=None means "leave unchanged"; send "" to blank

        await self._session.flush()
        return app_row

    async def add_note(
        self, user_id: uuid.UUID, application_id: uuid.UUID, body: str
    ) -> ApplicationEvent:
        await self.get(user_id, application_id)  # ownership + 404
        ev = ApplicationEvent(
            application_id=application_id, user_id=user_id, kind="note", body=body,
        )
        self._session.add(ev)
        await self._session.flush()
        return ev

    async def soft_delete(self, user_id: uuid.UUID, application_id: uuid.UUID) -> None:
        app_row = await self.get(user_id, application_id)
        app_row.deleted_at = datetime.now(UTC)
        await self._session.flush()
```

**NOTE for the implementer:** `case({mapping}, value=col, else_=99)` is verified working against the installed SQLAlchemy 2.0.52 (controller ran `from sqlalchemy import case; case({'a': 0}, value=literal_column('x'), else_=9)` — produced valid SQL). Use it as written above; no fallback needed.

- [ ] **Step 3: `tests/domain/applications/test_application_service.py`** (DB-gated, CI-only)
```python
"""ApplicationService -- DB integration, CI-deferred."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import NotFoundError, ValidationAppError
from app.domain.applications.service import ApplicationService
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.user import User


async def _seed(db_session, email):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="BE", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    a = Application(user_id=u.id, job_id=j.id, status="saved", source="user")
    db_session.add(a)
    await db_session.flush()
    return u, a


async def test_patch_status_writes_event_and_audit_and_sets_applied_at(db_session):
    u, a = await _seed(db_session, "svc-patch@x.com")
    svc = ApplicationService(db_session)
    out = await svc.patch(u.id, a.id, status="applied")
    assert out.status == "applied"
    assert out.applied_at is not None

    ev = (
        await db_session.execute(
            select(ApplicationEvent).where(ApplicationEvent.application_id == a.id)
        )
    ).scalar_one()
    assert ev.kind == "status_change" and ev.from_status == "saved" and ev.to_status == "applied"

    audit_rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "application.status_change")
        )
    ).scalars().all()
    assert any(r.resource_id == a.id for r in audit_rows)


async def test_patch_rejects_an_internal_status(db_session):
    u, a = await _seed(db_session, "svc-bad-status@x.com")
    with pytest.raises(ValidationAppError):
        await ApplicationService(db_session).patch(u.id, a.id, status="awaiting_approval")


async def test_get_and_list_hide_soft_deleted(db_session):
    u, a = await _seed(db_session, "svc-delete@x.com")
    svc = ApplicationService(db_session)
    await svc.soft_delete(u.id, a.id)
    with pytest.raises(NotFoundError):
        await svc.get(u.id, a.id)
    rows, total = await svc.list_(u.id)
    assert total == 0 and rows == []


async def test_add_note_creates_a_note_event(db_session):
    u, a = await _seed(db_session, "svc-note@x.com")
    ev = await ApplicationService(db_session).add_note(u.id, a.id, "Followed up by email")
    assert ev.kind == "note" and ev.body == "Followed up by email"


async def test_list_filters_by_status(db_session):
    u, a = await _seed(db_session, "svc-list@x.com")
    await ApplicationService(db_session).patch(u.id, a.id, status="interview")
    rows, total = await ApplicationService(db_session).list_(u.id, status="interview")
    assert total == 1 and rows[0].id == a.id
    rows2, total2 = await ApplicationService(db_session).list_(u.id, status="offer")
    assert total2 == 0


async def test_list_status_sort_runs(db_session):
    """Exercise the pipeline-rank case() expression against real Postgres."""
    u, a = await _seed(db_session, "svc-sort@x.com")
    rows, total = await ApplicationService(db_session).list_(u.id, sort="status")
    assert total == 1 and rows[0].id == a.id
```

- [ ] **Step 4: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: `lint-imports` `3 kept, 0 broken`; collection error-free.

```bash
git add backend/app/domain/applications backend/tests/domain/applications
git commit -m "feat(applications): ApplicationService -- list/get/patch/add_note/soft_delete + audit trail"
```

---

## Task 3: `ApplicationService.timeline` — the merge

**Files:** Modify `backend/app/domain/applications/service.py`, `backend/tests/domain/applications/test_application_service.py`.

**Interfaces:**
- Produces: `ApplicationService.timeline(user_id, application_id) -> list[TimelineItem]` where `TimelineItem` is a `@dataclass(frozen=True)` with `kind: str`, `at: datetime`, `title: str`, `detail: dict[str, Any]`.

- [ ] **Step 1: add to `service.py`** — the dataclass at module level and the method on the class:
```python
from dataclasses import dataclass
from typing import Any

from app.models.ai import AiAction


@dataclass(frozen=True)
class TimelineItem:
    kind: str
    at: datetime
    title: str
    detail: dict[str, Any]


def _event_title(e: ApplicationEvent) -> str:
    if e.kind == "status_change":
        return f"Moved to {e.to_status}"
    if e.kind == "note":
        return "Note added"
    if e.kind == "interview_scheduled":
        return "Interview scheduled"
    if e.kind == "email_sent":
        return "Application email sent"
    return e.body or "Mana AI action"
```
```python
    async def timeline(
        self, user_id: uuid.UUID, application_id: uuid.UUID
    ) -> list[TimelineItem]:
        app_row = await self.get(user_id, application_id)

        events = (
            await self._session.execute(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == application_id)
                .order_by(ApplicationEvent.occurred_at.desc())
            )
        ).scalars().all()

        items: list[TimelineItem] = []
        for e in events:
            detail = {
                k: v
                for k, v in {
                    "from": e.from_status, "to": e.to_status, "body": e.body,
                    **(e.meta or {}),
                }.items()
                if v is not None
            }
            items.append(
                TimelineItem(kind=e.kind, at=e.occurred_at, title=_event_title(e), detail=detail)
            )

        if app_row.ai_session_id is not None:
            actions = (
                await self._session.execute(
                    select(AiAction).where(
                        AiAction.user_id == user_id,
                        AiAction.ai_session_id == app_row.ai_session_id,
                    )
                )
            ).scalars().all()
            for a in actions:
                items.append(
                    TimelineItem(
                        kind="ai_action", at=a.occurred_at, title=a.summary,
                        detail=dict(a.detail or {}),
                    )
                )

        items.sort(key=lambda it: it.at, reverse=True)
        return items
```

**NOTE for the implementer:** `AiAction.occurred_at` is confirmed present (controller read `app/models/ai.py` — `TIMESTAMP(timezone=True)`, `server_default now()`). `AiAction.detail` is a non-null JSONB dict (`server_default '{}'`). Use `occurred_at` as written.

- [ ] **Step 2: extend `tests/domain/applications/test_application_service.py`**:
```python
async def test_timeline_merges_events_newest_first(db_session):
    u, a = await _seed(db_session, "svc-timeline@x.com")
    svc = ApplicationService(db_session)
    await svc.patch(u.id, a.id, status="applied")
    await svc.add_note(u.id, a.id, "Recruiter replied")

    items = await svc.timeline(u.id, a.id)
    kinds = [it.kind for it in items]
    assert "status_change" in kinds and "note" in kinds
    # newest first
    ats = [it.at for it in items]
    assert ats == sorted(ats, reverse=True)
```

- [ ] **Step 3: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: clean.

```bash
git add backend/app/domain/applications/service.py backend/tests/domain/applications/test_application_service.py
git commit -m "feat(applications): timeline() -- merge application_events + ai_actions newest-first"
```

---

## Task 4: schemas + `POST` intent + list/patch/delete routes

**Files:** Modify `backend/app/api/v1/schemas/applications.py`, `backend/app/api/v1/applications.py`.

**Interfaces:**
- Produces: `POST /applications` (`intent` union — 202 `RunRefOut` | 201 `ApplicationOut`); `GET /applications` (list); `PATCH /applications/{id}`; `DELETE /applications/{id}`.

- [ ] **Step 1: `schemas/applications.py`** — add `from typing import Any, Literal` to the imports and `Field` to the existing `from pydantic import BaseModel, ConfigDict` line. Add `intent` to the existing `ApplicationCreateIn` (in place). Add `notes` + `ai_session_id` to the existing `ApplicationOut` (in place). Append the four new classes **after** `ApplicationOut` (`ApplicationListOut` references it):
```python
class ApplicationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID
    intent: Literal["prepare", "save"] = "prepare"


class ApplicationPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["saved", "applied", "interview", "offer", "rejected", "withdrawn"] | None = None
    notes: str | None = None


class ApplicationNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)


class ApplicationListOut(BaseModel):
    items: list[ApplicationOut]
    total: int
    limit: int
    offset: int


class TimelineItemOut(BaseModel):
    kind: str
    at: dt.datetime
    title: str
    detail: dict[str, Any]


class ApplicationTimelineOut(BaseModel):
    items: list[TimelineItemOut]
```
Add `Field` to the pydantic import. `ApplicationOut` gains two fields:
```python
    notes: str | None
    ai_session_id: uuid.UUID | None
```

- [ ] **Step 2: replace the whole body of `app/api/v1/applications.py`** with the following. This drops the now-unused `from sqlalchemy import select` and `from app.core.errors import NotFoundError` imports (the service owns the 404), adds `Query` + `Response`, and keeps the `POST` decorator's documented `status_code=202` — the save branch overrides to 201 via `response.status_code`.
```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.ai import RunRefOut
from app.api.v1.schemas.applications import (
    ApplicationCreateIn,
    ApplicationListOut,
    ApplicationNoteIn,
    ApplicationOut,
    ApplicationPatchIn,
    ApplicationTimelineOut,
    TimelineItemOut,
)
from app.core.audit import audit
from app.domain.agents.service import AgentService
from app.domain.applications.service import ApplicationService
from app.models.application import Application
from app.models.application_event import ApplicationEvent

router = APIRouter(prefix="/applications", tags=["applications"])


def _application_out(a: Application) -> ApplicationOut:
    return ApplicationOut(
        id=a.id, job_id=a.job_id, resume_version_id=a.resume_version_id,
        cover_letter_id=a.cover_letter_id, application_email_id=a.application_email_id,
        status=a.status, match_score=a.match_score, source=a.source,
        applied_at=a.applied_at, last_status_change_at=a.last_status_change_at,
        notes=a.notes, ai_session_id=a.ai_session_id,
        created_at=a.created_at, updated_at=a.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_application(
    body: ApplicationCreateIn, db: DbDep, user: CurrentUser, response: Response
) -> RunRefOut | ApplicationOut:
    if body.intent == "save":
        app_row = Application(
            user_id=user.id, job_id=body.job_id, status="saved", source="user",
        )
        db.add(app_row)
        await db.flush()
        db.add(
            ApplicationEvent(
                application_id=app_row.id, user_id=user.id, kind="status_change",
                from_status=None, to_status="saved",
            )
        )
        await audit(
            db, actor_type="user", action="application.saved",
            actor_user_id=user.id, resource_type="application", resource_id=app_row.id,
        )
        await db.commit()
        response.status_code = status.HTTP_201_CREATED
        return _application_out(app_row)

    session = await AgentService(db).create_session(user.id, kind="agent_run")
    run_id = await AgentService(db).start_run(
        user.id, session.id, goal="prepare_application",
        inputs={"job_id": str(body.job_id)},
    )
    await db.commit()
    return RunRefOut(run_id=run_id, session_id=str(session.id))


@router.get("")
async def list_applications(
    db: DbDep,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = "recent",
    limit: int = 100,
    offset: int = 0,
) -> ApplicationListOut:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows, total = await ApplicationService(db).list_(
        user.id, status=status_filter, sort=sort, limit=limit, offset=offset,
    )
    return ApplicationListOut(
        items=[_application_out(r) for r in rows], total=total, limit=limit, offset=offset,
    )


@router.get("/{application_id}")
async def get_application(
    application_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ApplicationOut:
    return _application_out(await ApplicationService(db).get(user.id, application_id))


@router.patch("/{application_id}")
async def patch_application(
    application_id: uuid.UUID, body: ApplicationPatchIn, db: DbDep, user: CurrentUser
) -> ApplicationOut:
    row = await ApplicationService(db).patch(
        user.id, application_id, status=body.status, notes=body.notes,
    )
    return _application_out(row)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> None:
    await ApplicationService(db).soft_delete(user.id, application_id)
```
Task 5 appends the `/notes` and `/timeline` routes plus their two mapper helpers to this same file (its imports of `ApplicationNoteIn` / `ApplicationTimelineOut` / `TimelineItemOut` / `ApplicationEvent` are already in the block above, so Task 5 adds no new imports).

- [ ] **Step 3: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: clean. (No pure tests this task — DB-gated API tests are Task 6.)

```bash
git add backend/app/api/v1/schemas/applications.py backend/app/api/v1/applications.py
git commit -m "feat(applications): POST intent=save + GET list + PATCH + DELETE routes"
```

---

## Task 5: notes + timeline routes

**Files:** Modify `backend/app/api/v1/applications.py`.

**Interfaces:**
- Produces: `POST /applications/{id}/notes` → 201 `TimelineItemOut`; `GET /applications/{id}/timeline` → `ApplicationTimelineOut`.

- [ ] **Step 1: add to `applications.py`** — change the existing `from app.domain.applications.service import ApplicationService` line to `from app.domain.applications.service import ApplicationService, TimelineItem`. `ApplicationEvent` is already imported (Task 4). Then append these two helpers and two routes:
```python
def _timeline_item_out(it: TimelineItem) -> TimelineItemOut:
    return TimelineItemOut(kind=it.kind, at=it.at, title=it.title, detail=it.detail)


def _note_event_out(ev: ApplicationEvent) -> TimelineItemOut:
    return TimelineItemOut(
        kind="note", at=ev.occurred_at, title="Note added", detail={"body": ev.body or ""},
    )


@router.post("/{application_id}/notes", status_code=status.HTTP_201_CREATED)
async def add_application_note(
    application_id: uuid.UUID, body: ApplicationNoteIn, db: DbDep, user: CurrentUser
) -> TimelineItemOut:
    ev = await ApplicationService(db).add_note(user.id, application_id, body.body)
    return _note_event_out(ev)


@router.get("/{application_id}/timeline")
async def get_application_timeline(
    application_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ApplicationTimelineOut:
    items = await ApplicationService(db).timeline(user.id, application_id)
    return ApplicationTimelineOut(items=[_timeline_item_out(it) for it in items])
```

- [ ] **Step 2: gate + commit**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: clean.

```bash
git add backend/app/api/v1/applications.py
git commit -m "feat(applications): POST /{id}/notes + GET /{id}/timeline routes"
```

---

## Task 6: DB-gated API integration tests — SUBAGENT REVIEW (multi-file integration)

**Files:** Create `backend/tests/api/test_applications_tracker.py`.

**Interfaces:**
- Consumes: everything from Tasks 1-5. No production code.

- [ ] **Step 1:** read `tests/api/test_approvals.py` (Phase 10a) for the confirmed `_auth(client, email)` helper (register+login → bearer header dict — there is NO `auth_headers` fixture) and mirror it.

- [ ] **Step 2: `tests/api/test_applications_tracker.py`** (DB-gated, CI-only)
```python
"""/applications tracker routes -- DB integration, CI-deferred."""
from __future__ import annotations

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


async def test_save_intent_creates_a_saved_application(client, db_session):
    h = await _auth(client, "tr-save@x.com")
    job = await _seed_job(db_session)
    r = await client.post(
        "/api/v1/applications", headers=h, json={"job_id": str(job.id), "intent": "save"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "saved" and body["source"] == "user"


async def test_list_patch_timeline_note_delete_round_trip(client, db_session):
    h = await _auth(client, "tr-full@x.com")
    job = await _seed_job(db_session)
    created = (
        await client.post(
            "/api/v1/applications", headers=h,
            json={"job_id": str(job.id), "intent": "save"},
        )
    ).json()
    app_id = created["id"]

    lst = await client.get("/api/v1/applications", headers=h)
    assert lst.status_code == 200 and lst.json()["total"] == 1

    patched = await client.patch(
        f"/api/v1/applications/{app_id}", headers=h, json={"status": "applied"}
    )
    assert patched.status_code == 200 and patched.json()["status"] == "applied"
    assert patched.json()["applied_at"] is not None

    bad = await client.patch(
        f"/api/v1/applications/{app_id}", headers=h, json={"status": "awaiting_approval"}
    )
    assert bad.status_code == 422 or bad.status_code == 400

    note = await client.post(
        f"/api/v1/applications/{app_id}/notes", headers=h, json={"body": "Recruiter replied"}
    )
    assert note.status_code == 201 and note.json()["kind"] == "note"

    tl = await client.get(f"/api/v1/applications/{app_id}/timeline", headers=h)
    assert tl.status_code == 200
    kinds = [it["kind"] for it in tl.json()["items"]]
    assert "status_change" in kinds and "note" in kinds

    dele = await client.delete(f"/api/v1/applications/{app_id}", headers=h)
    assert dele.status_code == 204
    gone = await client.get(f"/api/v1/applications/{app_id}", headers=h)
    assert gone.status_code == 404


async def test_list_filters_by_status_and_hides_deleted(client, db_session):
    h = await _auth(client, "tr-filter@x.com")
    job = await _seed_job(db_session)
    a1 = (await client.post("/api/v1/applications", headers=h, json={"job_id": str(job.id), "intent": "save"})).json()
    a2 = (await client.post("/api/v1/applications", headers=h, json={"job_id": str(job.id), "intent": "save"})).json()
    await client.patch(f"/api/v1/applications/{a1['id']}", headers=h, json={"status": "interview"})

    only_interview = await client.get("/api/v1/applications?status=interview", headers=h)
    ids = {it["id"] for it in only_interview.json()["items"]}
    assert ids == {a1["id"]}

    await client.delete(f"/api/v1/applications/{a2['id']}", headers=h)
    all_ = await client.get("/api/v1/applications", headers=h)
    assert {it["id"] for it in all_.json()["items"]} == {a1["id"]}
```

- [ ] **Step 3: gate**

Run: `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only`
Expected: clean (DB test collects, not run locally).

```bash
git add backend/tests/api/test_applications_tracker.py
git commit -m "test(applications): tracker routes -- save/list/patch/timeline/note/delete (DB-gated)"
```

---

## Task 7: verification + whole-branch review + completion report + squash + push + CI

Controller-only. Mirror the Phase 8a/9/10a closeout: full local gate, run every pure suite added/modified (skip DB-gated files), whole-branch review (inline except the two subagent-reviewed tasks), write the completion report into this plan file with directly-verified baseline counts (isolated worktree), squash/fast-forward to `main`, push, watch CI (the `backend` job's DB suite is the real proof — watch for a `case()` construct error against real Postgres and for the migration `0014` applying cleanly), `finishing-a-development-branch`.

---

## Completion report (2026-09-06)

**Status: shipped.** All 7 tasks complete on `phase-11a-application-tracker-backend`, fast-forwarded to `main`.

### Commits (fast-forward, per-task commits already clean — no squash)

| SHA | Task | Summary |
|---|---|---|
| `8847479` | 1 | `application_events` table — migration `0014` + append-only model (`Base` only, `created_at` + `occurred_at`, no trigger; mirrors `audit_logs`) |
| `f9eb6b3` | 2 | `ApplicationService` — `list_` / `get` / `patch` / `add_note` / `soft_delete`; status change writes an `application_events` row + an `audit_logs` row (`application.status_change`) + `last_status_change_at`, and `applied_at` on first move to `applied` |
| `57d81a3` | 3 | `ApplicationService.timeline()` — merges `application_events` + `ai_actions` (only when `ai_session_id` set) into one newest-first `list[TimelineItem]` |
| `e834318` | 4 | schemas + `POST /applications` intent union (`prepare`→202 `RunRefOut` \| `save`→201 `ApplicationOut`, `save` writes a `status_change` event + `application.saved` audit) + `GET` list (`?status=&sort=&limit=&offset=`) + `PATCH` + `DELETE` (soft) |
| `cdb6ef5` | 5 | `POST /applications/{id}/notes` (201 `TimelineItemOut`) + `GET /applications/{id}/timeline` (`ApplicationTimelineOut`) |
| `12216be` | 6 | DB-gated API integration suite `tests/api/test_applications_tracker.py` (save/list/patch/timeline/note/delete round-trips) |

### Verification

- Baseline `51fbd99` (fork point), directly measured in the working tree: **159 mypy source files**, **414 tests collected**.
- Branch HEAD `12216be`: **162 mypy source files** (+3: `models/application_event.py`, `domain/applications/__init__.py`, `domain/applications/service.py`), **425 tests collected** (+11: 1 model round-trip, 7 `ApplicationService`, 3 API tracker).
- Local gate on HEAD: `ruff` clean · `mypy app` clean (162 files) · `lint-imports` **3 kept, 0 broken** (new `app.domain.applications` leaf imports only `app.core.*` / `app.models.*`) · `pytest --collect-only` 425, 0 errors.
- **DB-gated tests (11 new) run in CI only** — no local Postgres. Alembic chain single head `0014_application_events`.

### Rulings

- **R-T2-review** — Task 2 (`ApplicationService`) got a subagent review though the plan left it untagged: it is the phase's core status-change audit-trail logic and is DB-gated (no local test signal). Verdict: spec PASS, quality APPROVE, zero defects.
- **R-T4-review** — Task 4 (routes/schemas) reviewed inline rather than as a subagent "API wiring" review: it is a controller-authored full-file replacement pre-verified against `jobs.py` / `test_approvals.py`, and Task 6's subagent review independently exercises the whole HTTP surface. No double-coverage.
- **Whole-branch review: inline** (project lean-review convention). PASS — no integration issues. Checked: `_application_out` is the sole `ApplicationOut` constructor (2 new required fields safe); Phase 10a `test_applications.py` still green (no exact-body assertions; `POST` with no `intent` still 202); new response fields are additive/back-compat for the Phase 10b frontend; save-branch `db.commit()` matches the existing prepare-branch pattern; mutations flush-only via the request session like sibling domains; FastAPI route paths unambiguous.

### Deviations from plan (all gate-forced, behavior-neutral)

1. Task 2 test: `rows2, total2 = ...` → `_, total2 = ...` (ruff `RUF059`, matches repo throwaway-unpack convention).
2. Task 4: the 3 Task-5-only schema imports (`ApplicationNoteIn`, `ApplicationTimelineOut`, `TimelineItemOut`) were NOT added in Task 4 — ruff `F401` rejects unused imports even transiently. Task 5's brief was amended to add them (plus `TimelineItem`) when the routes that use them land.
3. Task 6 test: two 118-char `a1`/`a2` lines wrapped into the brief's own multiline `client.post(...)` form (ruff `E501`).
4. Task 5 was committed by the controller after its implementer agent died on a network error post-write, pre-commit — the uncommitted diff was verified verbatim-to-brief and the full gate re-run green before committing.
5. Infra (not a code change): a prior task rebuilt a broken `.venv` (its Python 3.12 interpreter had been removed from the system) from the unchanged `uv.lock`; `uv.lock` and all tracked files untouched, CI unaffected (builds its own env).

### Deferred to Phase 11b (frontend)

Kanban board `/applications`, detail page `/applications/[id]`, drag-and-drop status change with optimistic UI, timeline view, the "Applications" nav entry. Also still out of scope: a dedicated `interview_scheduled` endpoint, cursor pagination.
