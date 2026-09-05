"""``cover_letter`` -- write a grounded cover letter for the tailored résumé + job."""

import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.nodes.resume_tailoring import _summarise_job, _summarise_profile
from app.domain.agents.state import ManaState
from app.domain.generation.cover_letter import write_cover_letter
from app.domain.generation.service import GenerationService
from app.domain.jobs.service import JobService
from app.domain.profile.service import ProfileService
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.version_service import TailoringService
from app.models.application import CoverLetter

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def cover_letter(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    job_id = state["inputs"]["job_id"]
    version_id = state.get("tailored_resume_version_id")
    if not version_id:
        return {
            "status": "halted",
            "error": "no tailored résumé to write a cover letter from",
            "_summary": "Tailor a résumé first",
        }

    version = await TailoringService(deps.session).get_version(
        deps.user_id, uuid.UUID(version_id)
    )
    tailored = ResumeExtraction.model_validate(version.content)

    job = await JobService(deps.session).get(deps.user_id, job_id)
    profile, sections = await ProfileService(deps.session).load_full(deps.user_id)
    skills = await ProfileService(deps.session).list_skills(deps.user_id)
    profile_summary = _summarise_profile(profile, sections, skills)
    job_brief = _summarise_job(job)

    gen = GenerationService(deps.llm)
    draft, meta = await write_cover_letter(
        gen=gen, base=tailored, profile_summary=profile_summary, job_brief=job_brief
    )

    state["budget"]["llm_calls_made"] = state["budget"].get("llm_calls_made", 0) + 1
    state["budget"]["cost_usd"] = state["budget"].get("cost_usd", 0.0) + meta.cost_usd

    letter = CoverLetter(
        user_id=deps.user_id,
        job_id=job_id,
        resume_version_id=version.id,
        content=draft.content,
        content_json={
            "paragraphs": [p for p in draft.content.split("\n\n") if p.strip()]
        },
        generation_meta={
            "model": meta.model,
            "provider": meta.provider,
            "prompt_version": meta.prompt_version,
            "prompt_hash": meta.prompt_hash,
            "input_tokens": meta.input_tokens,
            "output_tokens": meta.output_tokens,
            "cost_usd": meta.cost_usd,
            "claim_validation": meta.claim_validation,
        },
        created_by="mana_ai",
    )
    deps.session.add(letter)
    await deps.session.flush()

    checked = meta.claim_validation.get("checked", 0)
    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="cover_letter",
        action_key="wrote_cover_letter",
        summary=f"Wrote a cover letter for {job.title} — {checked} claims checked",
    )

    return {
        "cover_letter_id": str(letter.id),
        "_summary": "Cover letter draft ready",
        "_detail": {"claim_validation": meta.claim_validation},
    }
