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
    _, total2 = await ApplicationService(db_session).list_(u.id, status="offer")
    assert total2 == 0


async def test_list_status_sort_runs(db_session):
    """Exercise the pipeline-rank case() expression against real Postgres."""
    u, a = await _seed(db_session, "svc-sort@x.com")
    rows, total = await ApplicationService(db_session).list_(u.id, sort="status")
    assert total == 1 and rows[0].id == a.id
