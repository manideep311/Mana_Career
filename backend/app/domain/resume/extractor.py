from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import AppError
from app.domain.llm.provider import LLMMessage, LLMProvider, LLMResult


class ExtractedExperience(BaseModel):
    company: str
    title: str
    employment_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    location: str | None = None
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)


class ExtractedEducation(BaseModel):
    institution: str
    degree: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    grade: str | None = None


class ExtractedProject(BaseModel):
    name: str
    description: str | None = None
    url: str | None = None
    highlights: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None


class ExtractedCertification(BaseModel):
    name: str
    issuer: str | None = None
    issued_date: str | None = None
    expires_date: str | None = None
    credential_id: str | None = None
    url: str | None = None


class ResumeExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    email: str | None = None
    location: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[ExtractedExperience] = Field(default_factory=list)
    education: list[ExtractedEducation] = Field(default_factory=list)
    projects: list[ExtractedProject] = Field(default_factory=list)
    certifications: list[ExtractedCertification] = Field(default_factory=list)


EXTRACTION_SYSTEM_PROMPT = (
    "Extract resume information from the provided text. Return only facts "
    "explicitly stated; do not infer or guess. For any information not present, "
    "use null for optional fields or empty lists for arrays. Always include "
    "every field in your response, even if null or empty."
)


class ResumeExtractor:
    def __init__(self, llm: LLMProvider, *, model: str) -> None:
        self._llm = llm
        self._model = model
        self.last_usage: LLMResult | None = None

    async def extract(self, text: str) -> ResumeExtraction:
        messages: list[LLMMessage] = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": text[:20000]},
        ]
        result = await self._llm.complete(
            messages, schema=ResumeExtraction, max_tokens=4096
        )
        self.last_usage = result
        if result.structured is None:
            raise AppError(code="resume.extraction_failed")
        return ResumeExtraction.model_validate(result.structured)
