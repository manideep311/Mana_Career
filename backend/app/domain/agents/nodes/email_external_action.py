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
    if application is None:
        return {
            "status": "halted",
            "error": "application record incomplete",
            "_summary": "This application is missing required data",
        }
    letter = await deps.session.get(CoverLetter, application.cover_letter_id)
    email = await deps.session.get(ApplicationEmail, application.application_email_id)
    if letter is None or email is None:
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
