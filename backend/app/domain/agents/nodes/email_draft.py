"""``email_draft`` -- draft the application email from the cover letter."""

import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.generation.email_draft import draft_email
from app.domain.generation.service import GenerationService
from app.domain.jobs.service import JobService
from app.models.application import ApplicationEmail, CoverLetter
from app.models.user import User

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def email_draft(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    letter_id = state.get("cover_letter_id")
    if not letter_id:
        return {
            "status": "halted",
            "error": "no cover letter to draft an email from",
            "_summary": "Write a cover letter first",
        }

    letter = await deps.session.get(CoverLetter, uuid.UUID(letter_id))
    if letter is None:
        return {
            "status": "halted",
            "error": "no cover letter to draft an email from",
            "_summary": "Write a cover letter first",
        }

    job = await JobService(deps.session).get(deps.user_id, letter.job_id)
    user = await deps.session.get(User, deps.user_id)
    applicant_name = (user.full_name if user else "") or ""

    gen = GenerationService(deps.llm)
    draft, meta = await draft_email(
        gen=gen,
        job_title=job.title or "",
        company=job.company or "",
        applicant_name=applicant_name,
        cover_letter_content=letter.content,
    )

    state["budget"]["llm_calls_made"] = state["budget"].get("llm_calls_made", 0) + 1
    state["budget"]["cost_usd"] = state["budget"].get("cost_usd", 0.0) + meta.cost_usd

    email = ApplicationEmail(
        user_id=deps.user_id,
        job_id=letter.job_id,
        subject=draft.subject,
        body=draft.body,
        generation_meta={
            "model": meta.model,
            "provider": meta.provider,
            "prompt_version": meta.prompt_version,
            "prompt_hash": meta.prompt_hash,
            "input_tokens": meta.input_tokens,
            "output_tokens": meta.output_tokens,
            "cost_usd": meta.cost_usd,
        },
    )
    deps.session.add(email)
    await deps.session.flush()

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="email_draft",
        action_key="drafted_email",
        summary=f"Drafted an application email for {job.title}",
    )

    return {
        "email_draft_id": str(email.id),
        "_summary": "Application email draft ready",
    }
