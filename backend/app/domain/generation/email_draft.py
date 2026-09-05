from __future__ import annotations

from pydantic import BaseModel

from app.domain.generation.service import GenerationService
from app.domain.generation.types import GenerationMeta

_EMAIL_SYSTEM = (
    "You write a short, professional application email that accompanies a "
    "cover letter. Keep it to 3-5 sentences: state the role being applied "
    "for, mention that the résumé and cover letter are attached, and close "
    "politely. Do not repeat the full cover letter verbatim. Return a "
    "subject line and the email body as plain text."
)
_EMAIL_PROMPT_VERSION = "email-draft-1"


class EmailDraft(BaseModel):
    subject: str
    body: str


async def draft_email(
    *,
    gen: GenerationService,
    job_title: str,
    company: str,
    applicant_name: str,
    cover_letter_content: str,
) -> tuple[EmailDraft, GenerationMeta]:
    user = (
        f"Job title: {job_title}\n"
        f"Company: {company}\n"
        f"Applicant name: {applicant_name}\n\n"
        f"Cover letter (for reference, do not repeat verbatim):\n{cover_letter_content}"
    )
    res = await gen.generate(
        system=_EMAIL_SYSTEM,
        user=user,
        schema=EmailDraft,
        prompt_version=_EMAIL_PROMPT_VERSION,
        max_tokens=400,
    )
    draft = EmailDraft.model_validate(res.structured)
    return draft, res.meta
