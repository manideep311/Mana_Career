"""``application_prep`` -- deterministic assembly of the approval snapshot.

Builds a hashable snapshot of everything the human is about to approve
(job, cover letter, drafted email) and persists it as a new ``Application`` +
a pending ``ApprovalRequest``. No LLM call. Runs once (guard()-wrapped,
normal node -- unlike ``human_approval``, this never re-executes on resume).
"""

import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.applications.snapshot import build_snapshot as _build_snapshot
from app.domain.applications.snapshot import hash_snapshot as _hash_snapshot
from app.domain.jobs.service import JobService
from app.models.application import Application, ApplicationEmail, ApprovalRequest, CoverLetter

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


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
