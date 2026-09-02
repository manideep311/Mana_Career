from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import AppError
from app.domain.llm.provider import LLMMessage, LLMProvider, LLMResult


class JDSkill(BaseModel):
    raw: str
    weight: float = 0.5


class JobExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    company: str | None = None
    company_domain: str | None = None
    location: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    description: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[JDSkill] = Field(default_factory=list)
    preferred_skills: list[JDSkill] = Field(default_factory=list)


EXTRACTION_SYSTEM_PROMPT = (
    "Extract structured facts from the job description. Return only what the "
    "text states; never infer. Use null for absent optional fields and empty "
    "lists for absent arrays. Always include every field. work_mode must be one "
    "of remote|hybrid|onsite or null. seniority must be one of "
    "intern|junior|mid|senior|staff|principal|lead|manager or null. "
    "salary_period must be one of year|month|day|hour or null. For "
    "required_skills and preferred_skills, give each skill a `raw` name as "
    "written and a `weight` from 0 to 1 for how central it is to the role."
)


class JobExtractor:
    def __init__(self, llm: LLMProvider, *, model: str) -> None:
        self._llm = llm
        self._model = model
        self.last_usage: LLMResult | None = None

    async def extract(self, text: str) -> JobExtraction:
        messages: list[LLMMessage] = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": text[:20000]},
        ]
        result = await self._llm.complete(messages, schema=JobExtraction, max_tokens=4096)
        self.last_usage = result
        if result.structured is None:
            raise AppError(code="job.extraction_failed")
        return JobExtraction.model_validate(result.structured)
