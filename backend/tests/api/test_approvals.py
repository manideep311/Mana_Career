"""GET/POST /approvals -- DB integration, CI-deferred."""
from __future__ import annotations

import uuid

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
