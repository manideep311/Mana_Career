"""Deliver an approved application email: at most once, to the right inbox.

Used by the agent's send step and by the "Try sending again" endpoint, so both
follow the same rules:

- the approval must still be ``approved`` and the content must still hash to
  what the person reviewed (including the recipient they typed);
- one attempt at a time: an attempt claims the email with a single
  conditional UPDATE (``sending``, committed before the mail server is
  contacted), so two callers racing each other can't both send;
- an attempt is never repeated automatically: one still within
  ``SENDING_GRACE`` is left alone (it may be mid-delivery), and one older than
  that is treated as interrupted and becomes ``failed`` with a note to check
  the inbox first (the stuck-job sweeper does the same if nobody asks);
- in ``redirect`` delivery (the safe default for a public demo) the email goes
  to the applicant's own inbox with a note naming the employer address;
- daily caps per user and overall keep a public deployment from being used to
  send mail in bulk.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import EMAIL_ADDRESS_RE, Settings
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.domain.applications.snapshot import build_snapshot, hash_snapshot
from app.domain.documents.renderer import DocumentRenderer, RenderFormat, RenderUnavailable
from app.domain.email.mime import InvalidEmailMessage
from app.domain.email.sender import EmailSender
from app.domain.email.smtp import EmailDeliveryError
from app.domain.email.types import EmailAttachment, EmailMessage
from app.domain.jobs.service import JobService
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.version_service import TailoringService
from app.models.application import Application, ApplicationEmail, ApprovalRequest, CoverLetter
from app.models.user import User

Delivery = Literal["redirect", "live"]

REDIRECT_NOTE = (
    "Mana Career demo: in the live product this email would be delivered to {who}. "
    "It was sent to you instead so you can see exactly what the employer would "
    "receive.\n\n---\n\n"
)
# Longer than any single delivery can take (each SMTP step is bounded by
# SMTP_TIMEOUT_SECONDS), so an attempt younger than this may still be running.
SENDING_GRACE = timedelta(minutes=10)

IN_PROGRESS = "This email is being sent right now. Check back in a moment."
INTERRUPTED = (
    "An earlier attempt to send this was interrupted, so it may or may not have been "
    "delivered. Check the inbox before sending it again."
)
NO_RECIPIENT = "Add who this should go to before sending."
USER_CAP = "You've reached today's sending limit. Try again tomorrow."
UNVERIFIED = (
    "Confirm your email address first: use the link we emailed you, or ask for a new "
    "one from the banner at the top of the page."
)
TOTAL_CAP = "This demo has reached today's sending limit. Try again tomorrow."


@dataclass(frozen=True)
class SendOutcome:
    status: Literal["sent", "failed", "halted", "in_progress"]
    message: str
    delivered_to: str | None = None


# ----------------------------------------------------------------- pure parts


def resume_filename(applicant_name: str) -> str:
    safe = re.sub(r"[^\w .-]", "", applicant_name).strip()
    return f"{safe} - Resume.pdf" if safe else "Resume.pdf"


def compose_message(
    *,
    applicant_name: str,
    applicant_email: str,
    to_email: str,
    to_name: str | None,
    subject: str,
    body: str,
    body_format: str,
    brand: str,
    delivery: Delivery,
    attachment: EmailAttachment | None,
) -> tuple[EmailMessage, str]:
    """The message to hand the sender, and the address it will really reach."""
    from_name = f"{applicant_name} via {brand}" if applicant_name.strip() else brand
    attachments = (attachment,) if attachment else ()
    if delivery == "redirect":
        who = f"{to_name} <{to_email}>" if to_name else to_email
        note = REDIRECT_NOTE.format(who=who)
        if body_format == "html":
            note = f"<p><em>{note.replace(chr(10), ' ').strip(' -')}</em></p><hr>"
        return (
            EmailMessage(
                to_email=applicant_email, to_name=applicant_name.strip() or None,
                subject=subject, body=note + body, body_format=body_format,
                from_name=from_name, reply_to=applicant_email, attachments=attachments,
            ),
            applicant_email,
        )
    copy = () if applicant_email.lower() == to_email.lower() else (applicant_email,)
    return (
        EmailMessage(
            to_email=to_email, to_name=to_name, subject=subject, body=body,
            body_format=body_format, from_name=from_name, reply_to=applicant_email,
            bcc=copy, attachments=attachments,
        ),
        to_email,
    )


def clean_recipient(to_email: str | None, to_name: str | None) -> tuple[str, str | None]:
    address = (to_email or "").strip()
    if not EMAIL_ADDRESS_RE.match(address) or len(address) > 320:
        raise ValidationAppError(
            "Enter a valid email address for the hiring contact.",
            code="application.recipient_invalid",
        )
    name = (to_name or "").strip() or None
    if name is not None and ("\r" in name or "\n" in name or len(name) > 200):
        raise ValidationAppError(
            "The contact name can't contain line breaks or exceed 200 characters.",
            code="application.recipient_invalid",
        )
    return address, name


def email_confirmation_required(user: User | None, settings: Settings) -> bool:
    """Real email goes out only for confirmed addresses, so an account created
    with someone else's address can't make the app email them."""
    return settings.email_provider == "smtp" and (user is None or user.email_verified_at is None)


# ----------------------------------------------------------------- data access


async def _parts(
    session: AsyncSession, application: Application
) -> tuple[CoverLetter, ApplicationEmail] | None:
    if application.cover_letter_id is None or application.application_email_id is None:
        return None
    letter = await session.get(CoverLetter, application.cover_letter_id)
    email = await session.get(ApplicationEmail, application.application_email_id)
    if letter is None or email is None:
        return None
    return letter, email


async def _snapshot(
    session: AsyncSession, user_id: uuid.UUID, application: Application,
    letter: CoverLetter, email: ApplicationEmail,
) -> tuple[dict[str, Any], str]:
    job = await JobService(session).get(user_id, application.job_id)
    snap = build_snapshot(
        job.title or "", job.company or "",
        str(application.resume_version_id) if application.resume_version_id else None,
        letter, email,
    )
    return snap, hash_snapshot(snap)


async def latest_approval(
    session: AsyncSession, application_id: uuid.UUID
) -> ApprovalRequest | None:
    return (
        await session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.application_id == application_id)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


async def _sending_since(session: AsyncSession, email_id: uuid.UUID) -> datetime:
    """When the current attempt started: the row's ``updated_at`` (kept by a
    trigger), read from the database rather than a possibly stale object."""
    return (
        await session.execute(
            select(ApplicationEmail.updated_at).where(ApplicationEmail.id == email_id)
        )
    ).scalar_one()


async def _claim(
    session: AsyncSession, email: ApplicationEmail, refs: dict[str, Any]
) -> bool:
    """Atomically take the email for this attempt. False if another attempt
    already holds it (or it has been sent) -- then the caller must not send."""
    claimed = (
        await session.execute(
            update(ApplicationEmail)
            .where(
                ApplicationEmail.id == email.id,
                ApplicationEmail.status.not_in(("sending", "sent")),
            )
            .values(status="sending", send_error=None, attachment_refs=refs)
            .returning(ApplicationEmail.id)
            # Update the in-session object only if this attempt won the claim.
            .execution_options(synchronize_session="fetch")
        )
    ).first()
    return claimed is not None


async def _sent_today(session: AsyncSession, user_id: uuid.UUID | None = None) -> int:
    start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    stmt = select(func.count()).select_from(ApplicationEmail).where(
        ApplicationEmail.status == "sent", ApplicationEmail.sent_at >= start
    )
    if user_id is not None:
        stmt = stmt.where(ApplicationEmail.user_id == user_id)
    return int((await session.execute(stmt)).scalar_one())


async def _resume_attachment(
    session: AsyncSession, user_id: uuid.UUID, application: Application, applicant_name: str
) -> tuple[EmailAttachment | None, dict[str, Any]]:
    if application.resume_version_id is None:
        return None, {"resume": "none"}
    try:
        version = await TailoringService(session).get_version(
            user_id, application.resume_version_id
        )
        doc = DocumentRenderer().render(
            ResumeExtraction.model_validate(version.content), RenderFormat.PDF
        )
    except (RenderUnavailable, NotFoundError, ValidationError):
        return None, {"resume": "unavailable"}
    name = resume_filename(applicant_name)
    return EmailAttachment(name, doc.media_type, doc.data), {"resume": name}


# ----------------------------------------------------------------- operations


async def set_approval_recipient(
    session: AsyncSession, *, user_id: uuid.UUID, approval: ApprovalRequest,
    to_email: str | None, to_name: str | None,
) -> None:
    """Record who the approved email goes to, so the approval covers it.

    Refuses if anything changed since the person opened the review (the stored
    hash no longer matches), then writes the recipient and re-hashes."""
    address, name = clean_recipient(to_email, to_name)
    application = await session.get(Application, approval.application_id)
    parts = await _parts(session, application) if application else None
    if application is None or parts is None:
        raise ConflictError("This application is missing required data.")
    letter, email = parts
    _, before = await _snapshot(session, user_id, application, letter, email)
    if before != approval.payload_hash:
        raise ConflictError(
            "This application changed after you opened it. Reload to review the latest "
            "version.",
            code="approval.changed",
        )
    email.to_email, email.to_name = address, name
    await session.flush()
    snap, after = await _snapshot(session, user_id, application, letter, email)
    approval.payload_snapshot = snap
    approval.payload_hash = after
    await session.flush()


async def _fail(
    session: AsyncSession, *, user_id: uuid.UUID, application: Application,
    email: ApplicationEmail, reason: str,
) -> SendOutcome:
    email.status = "failed"
    email.send_error = reason
    await session.flush()
    await audit(
        session, actor_type="mana_ai", action="application.email_failed", result="failure",
        on_behalf_of_user_id=user_id, resource_type="application", resource_id=application.id,
        meta={"application_email_id": str(email.id), "reason": reason},
    )
    return SendOutcome("failed", reason)


async def send_approved_application(
    session: AsyncSession, *, user_id: uuid.UUID, approval: ApprovalRequest,
    sender: EmailSender, settings: Settings, now: datetime | None = None,
) -> SendOutcome:
    now = now or datetime.now(UTC)
    if approval.status != "approved":
        return SendOutcome("halted", "This application hasn't been approved.")
    application = await session.get(Application, approval.application_id)
    if application is None or application.user_id != user_id:
        return SendOutcome("halted", "This application is missing required data.")
    parts = await _parts(session, application)
    if parts is None:
        return SendOutcome("halted", "This application is missing required data.")
    letter, email = parts
    _, current = await _snapshot(session, user_id, application, letter, email)
    if current != approval.payload_hash:
        return SendOutcome(
            "halted", "This application changed after you reviewed it. Please review it again."
        )

    if email.status == "sent":
        return SendOutcome("sent", "Already sent.", email.delivered_to)
    user = await session.get(User, user_id)
    if email.status == "sending":
        if await _sending_since(session, email.id) > now - SENDING_GRACE:
            return SendOutcome("in_progress", IN_PROGRESS)
        return await _fail(
            session, user_id=user_id, application=application, email=email, reason=INTERRUPTED
        )
    if not email.to_email:
        return await _fail(
            session, user_id=user_id, application=application, email=email, reason=NO_RECIPIENT
        )
    if email_confirmation_required(user, settings):
        return await _fail(
            session, user_id=user_id, application=application, email=email, reason=UNVERIFIED
        )
    if await _sent_today(session, user_id) >= settings.email_daily_limit_per_user:
        return await _fail(
            session, user_id=user_id, application=application, email=email, reason=USER_CAP
        )
    if await _sent_today(session) >= settings.email_daily_limit_total:
        return await _fail(
            session, user_id=user_id, application=application, email=email, reason=TOTAL_CAP
        )

    applicant_name = (user.full_name if user else "") or ""
    applicant_email = user.email if user else ""
    attachment, refs = await _resume_attachment(session, user_id, application, applicant_name)
    delivery: Delivery = settings.email_delivery
    message, delivered_to = compose_message(
        applicant_name=applicant_name, applicant_email=applicant_email,
        to_email=email.to_email, to_name=email.to_name, subject=email.subject,
        body=email.body, body_format=email.body_format, brand=settings.email_from_name,
        delivery=delivery, attachment=attachment,
    )

    # Claim and commit the attempt before contacting the mail server: a racing
    # caller loses the claim, and if this process dies mid-send the next caller
    # sees "sending" and won't send a second copy.
    if not await _claim(session, email, refs):
        await session.refresh(email)
        if email.status == "sent":
            return SendOutcome("sent", "Already sent.", email.delivered_to)
        return SendOutcome("in_progress", IN_PROGRESS)
    await session.commit()

    try:
        result = await sender.send(message)
    except (EmailDeliveryError, InvalidEmailMessage) as exc:
        return await _fail(
            session, user_id=user_id, application=application, email=email, reason=str(exc)
        )

    # The console sender only logs: nothing reached any inbox, so record none.
    reached = None if result.provider == "console" else delivered_to
    now = datetime.now(UTC)
    email.status = "sent"
    email.provider = result.provider
    email.provider_message_id = result.provider_message_id[:200]
    email.sent_at = now
    email.delivered_to = reached
    application.status = "applied"
    application.applied_at = now
    application.last_status_change_at = now
    await session.flush()
    await audit(
        session, actor_type="mana_ai", action="application.email_sent",
        on_behalf_of_user_id=user_id, resource_type="application", resource_id=application.id,
        meta={
            "provider": result.provider, "application_email_id": str(email.id),
            "redirected": delivery == "redirect",
        },
    )
    if reached is None:
        return SendOutcome("sent", "Recorded as sent (this server doesn't send real email)")
    if delivery == "redirect":
        return SendOutcome(
            "sent", f"Delivered to your inbox as a demo of the email to {email.to_email}", reached
        )
    return SendOutcome("sent", f"Sent to {email.to_email}", reached)
