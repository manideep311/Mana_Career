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
    import pytest
    from sqlalchemy.exc import IntegrityError

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
