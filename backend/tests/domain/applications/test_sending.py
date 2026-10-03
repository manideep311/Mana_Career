"""send_approved_application / set_approval_recipient -- DB integration, CI-deferred.

At most once, to the right inbox, only for what was approved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.core.errors import ConflictError, ValidationAppError
from app.domain.applications.sending import (
    IN_PROGRESS,
    INTERRUPTED,
    NO_RECIPIENT,
    SENDING_GRACE,
    USER_CAP,
    send_approved_application,
    set_approval_recipient,
)
from app.domain.applications.snapshot import build_snapshot, hash_snapshot
from app.domain.email.smtp import EmailDeliveryError
from app.domain.email.types import EmailMessage, EmailSendResult
from app.models.application import Application, ApplicationEmail, ApprovalRequest, CoverLetter
from app.models.job import Job
from app.models.user import User


@dataclass
class _RecordingSender:
    fail: Exception | None = None
    sent: list[EmailMessage] = field(default_factory=list)

    async def send(self, message: EmailMessage) -> EmailSendResult:
        if self.fail is not None:
            raise self.fail
        self.sent.append(message)
        return EmailSendResult(provider="test", provider_message_id=f"<{len(self.sent)}@t>")


async def _seed(db_session, address: str, *, approved: bool = True):
    user = User(email=address, password_hash="x", full_name="Asha Rao")
    job = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add_all([user, job])
    await db_session.flush()
    letter = CoverLetter(user_id=user.id, job_id=job.id, content="Dear Acme, ...")
    email = ApplicationEmail(
        user_id=user.id, job_id=job.id, subject="Application: Backend Engineer",
        body="Hello, my application is attached.",
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
        db_session, user_id=user.id, approval=approval,
        to_email="hiring@acme.test", to_name="Hiring Team",
    )
    if approved:
        approval.status = "approved"
        approval.decided_at = datetime.now(UTC)
        await db_session.flush()
    return user, application, email, approval


async def _send(db_session, user, approval, sender, *, now=None, **settings_over):
    settings = get_settings().model_copy(update=settings_over)
    return await send_approved_application(
        db_session, user_id=user.id, approval=approval, sender=sender, settings=settings,
        now=now,
    )


async def test_recipient_is_covered_by_the_approval_hash(db_session):
    _user, _app, email, approval = await _seed(db_session, "send-hash@x.com", approved=False)
    assert email.to_email == "hiring@acme.test"
    assert approval.payload_snapshot["email"]["to_email"] == "hiring@acme.test"
    # Editing anything afterwards means the stored hash no longer matches.
    email.body = "Something else"
    await db_session.flush()
    with pytest.raises(ConflictError):
        await set_approval_recipient(
            db_session, user_id=_user.id, approval=approval, to_email="x@y.test", to_name=None
        )


async def test_bad_recipients_are_refused(db_session):
    user, _app, _email, approval = await _seed(db_session, "send-bad@x.com", approved=False)
    for bad in ("", "no-at-sign", "a@b.test\r\nBcc: v@evil.test"):
        with pytest.raises(ValidationAppError):
            await set_approval_recipient(
                db_session, user_id=user.id, approval=approval, to_email=bad, to_name=None
            )


async def test_redirect_mode_delivers_to_the_applicant_once(db_session):
    user, application, email, approval = await _seed(db_session, "send-redirect@x.com")
    sender = _RecordingSender()
    outcome = await _send(db_session, user, approval, sender, email_delivery="redirect")
    assert outcome.status == "sent" and outcome.delivered_to == "send-redirect@x.com"
    assert sender.sent[0].to_email == "send-redirect@x.com"
    assert "hiring@acme.test" in sender.sent[0].body.splitlines()[0]
    assert (email.status, email.delivered_to, application.status) == (
        "sent", "send-redirect@x.com", "applied",
    )
    # A retry (or a re-run node) never sends a second copy.
    again = await _send(db_session, user, approval, sender)
    assert again.status == "sent" and len(sender.sent) == 1


async def test_live_mode_goes_to_the_employer_with_a_copy(db_session):
    user, _app, email, approval = await _seed(db_session, "send-live@x.com")
    sender = _RecordingSender()
    await _send(db_session, user, approval, sender, email_delivery="live")
    assert sender.sent[0].to_email == "hiring@acme.test"
    assert sender.sent[0].bcc == ("send-live@x.com",)
    assert email.delivered_to == "hiring@acme.test"


async def test_an_interrupted_attempt_is_never_resent(db_session):
    user, _app, email, approval = await _seed(db_session, "send-interrupted@x.com")
    email.status = "sending"  # a previous process died mid-send...
    await db_session.flush()
    sender = _RecordingSender()
    later = datetime.now(UTC) + SENDING_GRACE + SENDING_GRACE  # ...a while ago
    outcome = await _send(db_session, user, approval, sender, now=later)
    assert outcome.status == "failed" and outcome.message == INTERRUPTED
    assert sender.sent == [] and email.status == "failed"


async def test_an_attempt_still_in_flight_is_left_alone(db_session):
    user, _app, email, approval = await _seed(db_session, "send-inflight@x.com")
    email.status = "sending"  # another worker started moments ago
    await db_session.flush()
    sender = _RecordingSender()
    outcome = await _send(db_session, user, approval, sender)
    assert outcome.status == "in_progress" and outcome.message == IN_PROGRESS
    assert sender.sent == [] and email.status == "sending"  # not marked failed


async def test_a_caller_that_loses_the_race_does_not_send(db_session):
    user, _app, email, approval = await _seed(db_session, "send-race@x.com")
    # Another caller claims the email between our read and our claim: the row
    # changes in the database while this session's object still says "draft".
    await db_session.execute(
        update(ApplicationEmail)
        .where(ApplicationEmail.id == email.id)
        .values(status="sending")
        .execution_options(synchronize_session=False)
    )
    assert email.status != "sending"
    sender = _RecordingSender()
    outcome = await _send(db_session, user, approval, sender)
    assert outcome.status == "in_progress"
    assert sender.sent == [] and email.status == "sending"


async def test_mail_server_failure_is_recorded_not_retried(db_session):
    user, application, email, approval = await _seed(db_session, "send-fail@x.com")
    sender = _RecordingSender(fail=EmailDeliveryError("The mail server rejected the recipient."))
    outcome = await _send(db_session, user, approval, sender)
    assert outcome.status == "failed"
    assert email.status == "failed" and "rejected" in (email.send_error or "")
    assert application.status == "awaiting_approval"


async def test_unapproved_or_changed_applications_are_not_sent(db_session):
    user, _app, email, approval = await _seed(db_session, "send-gate@x.com", approved=False)
    sender = _RecordingSender()
    assert (await _send(db_session, user, approval, sender)).status == "halted"
    approval.status = "approved"
    email.subject = "Edited after review"
    await db_session.flush()
    assert (await _send(db_session, user, approval, sender)).status == "halted"
    assert sender.sent == []


async def test_missing_recipient_fails_clearly(db_session):
    user, application, email, approval = await _seed(db_session, "send-norcpt@x.com")
    email.to_email = None
    letter = await db_session.get(CoverLetter, application.cover_letter_id)
    approval.payload_hash = hash_snapshot(
        build_snapshot("Backend Engineer", "Acme", None, letter, email)
    )
    await db_session.flush()
    outcome = await _send(db_session, user, approval, _RecordingSender())
    assert outcome.status == "failed" and outcome.message == NO_RECIPIENT


async def test_daily_cap_per_user(db_session):
    user, _app, _email, approval = await _seed(db_session, "send-cap@x.com")
    outcome = await _send(
        db_session, user, approval, _RecordingSender(), email_daily_limit_per_user=0
    )
    assert outcome.status == "failed" and outcome.message == USER_CAP


async def test_real_email_needs_a_confirmed_address(db_session):
    from app.domain.applications.sending import UNVERIFIED

    user, _app, email, approval = await _seed(db_session, "send-unverified@x.com")
    sender = _RecordingSender()
    outcome = await _send(db_session, user, approval, sender, email_provider="smtp")
    assert outcome.status == "failed" and outcome.message == UNVERIFIED
    assert sender.sent == [] and email.status == "failed"

    user.email_verified_at = datetime.now(UTC)
    email.status = "failed"
    await db_session.flush()
    assert (await _send(db_session, user, approval, sender, email_provider="smtp")).status == "sent"
