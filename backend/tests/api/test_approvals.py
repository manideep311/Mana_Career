"""GET/POST /approvals -- DB integration, CI-deferred."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.applications.snapshot import build_snapshot, hash_snapshot
from app.models.application import (
    Application,
    ApplicationEmail,
    ApprovalRequest,
    CoverLetter,
)
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


async def test_decide_approval_rejects_a_second_decision(client, db_session):
    # `AgentService.start_run` / `resume_run` both `await enqueue(...)` a real
    # ARQ job; conftest's autouse `_no_enqueue` fixture already patches
    # `app.domain.agents.service.enqueue` to an async no-op, so this test only
    # has to exercise the ApprovalRequest state machine + the route's ownership
    # and idempotency checks -- no re-patch needed here.
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
    approval = await _seed_reviewable(db_session, user, job)

    r1 = await client.post(
        f"/api/v1/approvals/{approval.id}", headers=h, json=_APPROVE
    )
    assert r1.status_code == 202

    r2 = await client.post(
        f"/api/v1/approvals/{approval.id}", headers=h, json=_APPROVE
    )
    assert r2.status_code == 409


_APPROVE = {"decision": "approve", "to_email": "hiring@acme.test", "to_name": "Hiring Team"}


async def _seed_reviewable(db_session, user, job):
    """A paused prepare_application run whose approval hashes the real content."""
    from app.domain.agents.service import AgentService

    letter = CoverLetter(user_id=user.id, job_id=job.id, content="Dear Acme, ...")
    email = ApplicationEmail(
        user_id=user.id, job_id=job.id, subject="Application", body="Hello, attached."
    )
    db_session.add_all([letter, email])
    await db_session.flush()
    application = Application(
        user_id=user.id, job_id=job.id, status="awaiting_approval",
        cover_letter_id=letter.id, application_email_id=email.id,
    )
    db_session.add(application)
    await db_session.flush()
    session = await AgentService(db_session).create_session(user.id, kind="agent_run")
    await AgentService(db_session).start_run(
        user.id, session.id, goal="prepare_application", inputs={"job_id": str(job.id)}
    )
    await db_session.refresh(session)
    session.status = "awaiting_approval"
    snap = build_snapshot(job.title or "", job.company or "", None, letter, email)
    approval = ApprovalRequest(
        user_id=user.id, application_id=application.id, ai_session_id=session.id,
        run_id=session.run_id, payload_snapshot=snap, payload_hash=hash_snapshot(snap),
    )
    db_session.add(approval)
    await db_session.flush()
    return approval


async def _decide_setup(client, db_session, address):
    h = await _auth(client, address)
    user = (
        await db_session.execute(select(User).where(User.email == address))
    ).scalar_one()
    job = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(job)
    await db_session.flush()
    return h, await _seed_reviewable(db_session, user, job)


async def test_approving_records_the_recipient_inside_the_approval(client, db_session):
    h, approval = await _decide_setup(client, db_session, "approval-recipient@x.com")
    r = await client.post(f"/api/v1/approvals/{approval.id}", headers=h, json=_APPROVE)
    assert r.status_code == 202
    await db_session.refresh(approval)
    assert approval.status == "approved"
    assert approval.payload_snapshot["email"]["to_email"] == "hiring@acme.test"


async def test_approving_without_a_recipient_is_refused(client, db_session):
    h, approval = await _decide_setup(client, db_session, "approval-norecipient@x.com")
    r = await client.post(
        f"/api/v1/approvals/{approval.id}", headers=h, json={"decision": "approve"}
    )
    assert r.status_code == 422
    bad = await client.post(
        f"/api/v1/approvals/{approval.id}", headers=h,
        json={**_APPROVE, "to_email": "hiring@acme.test" + chr(13) + chr(10) + "Bcc: v@evil.test"},
    )
    assert bad.status_code == 422
    await db_session.refresh(approval)
    assert approval.status == "pending"


async def test_rejecting_needs_no_recipient(client, db_session):
    h, approval = await _decide_setup(client, db_session, "approval-reject@x.com")
    r = await client.post(
        f"/api/v1/approvals/{approval.id}", headers=h, json={"decision": "reject"}
    )
    assert r.status_code == 202


async def test_content_changed_since_review_blocks_approval(client, db_session):
    h, approval = await _decide_setup(client, db_session, "approval-changed@x.com")
    approval.payload_hash = "b" * 64  # the reviewed content no longer matches
    await db_session.flush()
    r = await client.post(f"/api/v1/approvals/{approval.id}", headers=h, json=_APPROVE)
    assert r.status_code == 409
    assert r.json()["code"] == "approval.changed"


async def test_approval_needs_a_confirmed_email_when_real_mail_is_on(
    client, db_session, monkeypatch
):
    from app.core.config import get_settings

    h, approval = await _decide_setup(client, db_session, "approval-unverified@x.com")
    # Scoped: only these env changes are undone, and the settings cache is
    # cleared on both sides so no other test sees SMTP settings.
    with monkeypatch.context() as mp:
        mp.setenv("EMAIL_PROVIDER", "smtp")
        mp.setenv("SMTP_HOST", "smtp.example.com")
        mp.setenv("EMAIL_FROM_ADDRESS", "applications@example.com")
        get_settings.cache_clear()
        try:
            r = await client.post(f"/api/v1/approvals/{approval.id}", headers=h, json=_APPROVE)
        finally:
            get_settings.cache_clear()
    get_settings.cache_clear()
    assert r.status_code == 409
    assert r.json()["code"] == "email_unverified"
    await db_session.refresh(approval)
    assert approval.status == "pending"

