"""GET /applications/{id}/delivery and POST /applications/{id}/send -- DB, CI-deferred."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.applications.sending import set_approval_recipient
from app.domain.applications.snapshot import build_snapshot, hash_snapshot
from app.models.application import Application, ApplicationEmail, ApprovalRequest, CoverLetter
from app.models.job import Job
from app.models.user import User


async def _auth(client, email):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "Asha Rao"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _approved_application(db_session, address: str, *, email_status: str):
    user = (await db_session.execute(select(User).where(User.email == address))).scalar_one()
    job = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(job)
    await db_session.flush()
    letter = CoverLetter(user_id=user.id, job_id=job.id, content="Dear Acme, ...")
    email = ApplicationEmail(
        user_id=user.id, job_id=job.id, subject="Application", body="Hello, attached."
    )
    db_session.add_all([letter, email])
    await db_session.flush()
    application = Application(
        user_id=user.id, job_id=job.id, status="awaiting_approval", source="mana_ai",
        cover_letter_id=letter.id, application_email_id=email.id,
    )
    db_session.add(application)
    await db_session.flush()
    snap = build_snapshot("Backend Engineer", "Acme", None, letter, email)
    approval = ApprovalRequest(
        user_id=user.id, application_id=application.id, ai_session_id=application.id,
        run_id=f"run-{application.id.hex}", payload_snapshot=snap,
        payload_hash=hash_snapshot(snap),
    )
    db_session.add(approval)
    await db_session.flush()
    await set_approval_recipient(
        db_session, user_id=user.id, approval=approval, to_email="hiring@acme.test", to_name=None
    )
    approval.status = "approved"
    approval.decided_at = datetime.now(UTC)
    email.status = email_status
    email.send_error = "The mail server didn't respond." if email_status == "failed" else None
    await db_session.flush()
    return application, email


async def test_delivery_reports_a_failure_and_a_retry_sends_it(client, db_session):
    h = await _auth(client, "delivery-retry@x.com")
    application, _email = await _approved_application(
        db_session, "delivery-retry@x.com", email_status="failed"
    )

    before = await client.get(f"/api/v1/applications/{application.id}/delivery", headers=h)
    assert before.status_code == 200
    assert before.json()["status"] == "failed"
    assert before.json()["error"] == "The mail server didn't respond."
    assert before.json()["intended_to"] == "hiring@acme.test"

    r = await client.post(f"/api/v1/applications/{application.id}/send", headers=h)
    assert r.status_code == 200
    body = r.json()
    # Tests run with the console sender: sent, but it reached no inbox.
    assert body["status"] == "sent"
    assert body["error"] is None
    assert body["delivered_to"] is None and body["redirected"] is False
    await db_session.refresh(application)
    assert application.status == "applied"


async def test_only_a_failed_send_can_be_retried(client, db_session):
    h = await _auth(client, "delivery-noretry@x.com")
    application, _email = await _approved_application(
        db_session, "delivery-noretry@x.com", email_status="sending"
    )
    r = await client.post(f"/api/v1/applications/{application.id}/send", headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "application.not_retryable"


async def test_another_user_cannot_see_or_send_it(client, db_session):
    await _auth(client, "delivery-owner@x.com")
    application, _email = await _approved_application(
        db_session, "delivery-owner@x.com", email_status="failed"
    )
    intruder = await _auth(client, "delivery-intruder@x.com")
    assert (
        await client.get(f"/api/v1/applications/{application.id}/delivery", headers=intruder)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/applications/{application.id}/send", headers=intruder)
    ).status_code == 404
