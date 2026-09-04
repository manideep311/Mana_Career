"""``resume_tailoring`` -- rewrite the user's confirmed résumé to fit a job.

Loads the user's confirmed résumé and the target job, runs the LLM-tailoring
+ claim-validation loop (:func:`app.domain.resume.tailoring.tailor_resume`),
and persists the draft as a new ``ai_tailored`` ``ResumeVersion``.
"""

from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.generation.service import GenerationService
from app.domain.jobs.service import JobService
from app.domain.profile.service import ProfileService
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.service import ResumeService
from app.domain.resume.tailoring import tailor_resume
from app.domain.resume.version_service import TailoringService
from app.models.job import Job
from app.models.profile import CareerProfile

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps

_MAX_PROFILE_CHARS = 1500
_MAX_JOB_CHARS = 6000


def _summarise_profile(
    profile: CareerProfile,
    sections: dict[str, list[Any]],
    skills: list[Any],
) -> str:
    parts: list[str] = []
    if profile.location:
        parts.append(f"Location: {profile.location}")
    if profile.preferred_roles:
        parts.append(f"Preferred roles: {', '.join(profile.preferred_roles)}")
    if profile.years_experience is not None:
        parts.append(f"Years of experience: {profile.years_experience}")
    if profile.seniority:
        parts.append(f"Seniority: {profile.seniority}")
    if profile.career_goals:
        parts.append(f"Career goals: {profile.career_goals}")

    for exp in sections.get("experiences", []):
        bits = [f"{exp.title} at {exp.company}"]
        if exp.description:
            bits.append(exp.description)
        if exp.highlights:
            bits.append("; ".join(exp.highlights))
        parts.append(" - ".join(bits))

    if skills:
        labels = [skill.label for _profile_skill, skill in skills]
        parts.append(f"Skills: {', '.join(labels)}")

    text = "\n".join(parts)
    return text[:_MAX_PROFILE_CHARS]


def _summarise_job(job: Job) -> str:
    parts = [p for p in (job.title, job.company) if p]
    if job.description:
        parts.append(job.description)
    if job.required_skills:
        skill_labels = [s.get("label", "") for s in job.required_skills if s.get("label")]
        if skill_labels:
            parts.append("Required skills: " + ", ".join(skill_labels))
    text = "\n".join(parts)
    return text[:_MAX_JOB_CHARS]


async def resume_tailoring(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    job_id = state["inputs"]["job_id"]

    resumes = await ResumeService(deps.session).list_(deps.user_id)
    confirmed = [r for r in resumes if r.confirmed_at is not None]
    chosen = next((r for r in confirmed if r.is_primary), confirmed[0] if confirmed else None)
    if chosen is None:
        return {
            "status": "halted",
            "error": "no confirmed résumé to tailor",
            "_summary": "Add a résumé first",
        }

    job = await JobService(deps.session).get(deps.user_id, job_id)
    profile, sections = await ProfileService(deps.session).load_full(deps.user_id)
    skills = await ProfileService(deps.session).list_skills(deps.user_id)
    profile_summary = _summarise_profile(profile, sections, skills)
    job_brief = _summarise_job(job)

    base = ResumeExtraction.model_validate(chosen.extraction or {})
    gen = GenerationService(deps.llm)
    tailored, meta = await tailor_resume(
        gen=gen, base=base, profile_summary=profile_summary, job_brief=job_brief
    )

    state["budget"]["llm_calls_made"] = state["budget"].get("llm_calls_made", 0) + 1
    state["budget"]["cost_usd"] = state["budget"].get("cost_usd", 0.0) + meta.cost_usd

    version = await TailoringService(deps.session).write_version(
        user_id=deps.user_id,
        resume_id=chosen.id,
        job_id=job_id,
        parent_version_id=None,
        kind="ai_tailored",
        content=tailored.model_dump(mode="json"),
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

    checked = meta.claim_validation.get("checked", 0)
    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="resume_tailoring",
        action_key="tailored_resume",
        summary=f"Tailored your résumé for {job.title} — {checked} claims checked",
    )

    return {
        "tailored_resume_version_id": str(version.id),
        "_summary": "Tailored résumé draft ready",
        "_detail": {"claim_validation": meta.claim_validation},
    }
