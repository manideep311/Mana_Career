from __future__ import annotations

import json
from dataclasses import replace

from pydantic import BaseModel

from app.domain.generation.service import GenerationService
from app.domain.generation.types import GenerationMeta
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.tailoring import MAX_CLAIM_REPROMPTS, ClaimValidator, _split_sentences

_LETTER_SYSTEM = (
    "You write a concise, professional cover letter for a job application. "
    "You may reference the candidate's experience, skills, and projects from "
    "the provided résumé and profile, and may reference the job posting. You "
    "must NOT invent employers, titles, dates, metrics, technologies, or "
    "accomplishments that are not already present in the provided résumé and "
    "profile. Return the full letter body as plain text, 3-5 short paragraphs "
    "separated by blank lines. Do not include a salutation placeholder like "
    "'[Hiring Manager]' -- address it generically ('Dear Hiring Team,')."
)
_LETTER_PROMPT_VERSION = "cover-letter-1"


class CoverLetterDraft(BaseModel):
    content: str


def _collect_sources(base: ResumeExtraction, profile_summary: str, job_brief: str) -> list[str]:
    """Sources a cover letter's claims may draw on.

    Deliberately NOT shared with ``resume.tailoring._collect_sources``: a
    cover letter may also reference the job posting itself ("your team's
    focus on X excites me"), which is not a valid grounding source when
    tailoring a résumé (the job is what you're tailoring *toward*, not a
    claim about the candidate).
    """
    sources: list[str] = []

    def _add(*values: str | None) -> None:
        for v in values:
            if v and v.strip():
                sources.append(v)

    _add(base.summary)
    for exp in base.experiences:
        _add(exp.description, exp.title, exp.company)
        sources.extend(h for h in exp.highlights if h and h.strip())
        sources.extend(t for t in exp.tech if t and t.strip())
    for proj in base.projects:
        _add(proj.description, proj.name)
        sources.extend(h for h in proj.highlights if h and h.strip())
        sources.extend(t for t in proj.tech if t and t.strip())
    for edu in base.education:
        _add(edu.institution, edu.degree, edu.field)
    for cert in base.certifications:
        _add(cert.name, cert.issuer)
    sources.extend(s for s in base.skills if s and s.strip())
    if profile_summary and profile_summary.strip():
        sources.extend(_split_sentences(profile_summary))
    if job_brief and job_brief.strip():
        sources.extend(_split_sentences(job_brief))
    return sources


def _render_prompt(
    base: ResumeExtraction,
    profile_summary: str,
    job_brief: str,
    tone: str,
    rejected: list[str] | None,
) -> str:
    base_json = json.dumps(base.model_dump(mode="json"), indent=2)
    parts = [
        f"Base résumé (JSON):\n{base_json}",
        f"Candidate profile summary:\n{profile_summary}",
        f"Target job:\n{job_brief}",
        f"Tone: {tone}",
    ]
    if rejected:
        rejected_lines = "\n".join(f"- {line}" for line in rejected)
        parts.append(
            "The following lines were not grounded in the source material; "
            f"rewrite or drop them:\n{rejected_lines}"
        )
    return "\n\n".join(parts)


async def write_cover_letter(
    *,
    gen: GenerationService,
    base: ResumeExtraction,
    profile_summary: str,
    job_brief: str,
    tone: str = "professional",
) -> tuple[CoverLetterDraft, GenerationMeta]:
    sources = _collect_sources(base, profile_summary, job_brief)
    validator = ClaimValidator(sources)
    user = _render_prompt(base, profile_summary, job_brief, tone, rejected=None)
    for attempt in range(MAX_CLAIM_REPROMPTS + 1):
        res = await gen.generate(
            system=_LETTER_SYSTEM,
            user=user,
            schema=CoverLetterDraft,
            prompt_version=_LETTER_PROMPT_VERSION,
            max_tokens=900,
        )
        draft = CoverLetterDraft.model_validate(res.structured)
        report = validator.check(_split_sentences(draft.content))
        meta = replace(res.meta, claim_validation=report.as_dict())
        if report.passed or attempt == MAX_CLAIM_REPROMPTS:
            return draft, meta
        user = _render_prompt(base, profile_summary, job_brief, tone, rejected=report.unsupported)
    raise AssertionError("unreachable")
