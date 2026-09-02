from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

WorkMode = Literal["remote", "hybrid", "onsite"]
Seniority = Literal["junior", "mid", "senior", "staff", "lead", "principal"]
SalaryPeriod = Literal["year", "month"]
Source = Literal["user", "resume_extraction"]


def _check_http_url(v: object) -> str | None:
    if v is None or v == "":
        return None
    if not isinstance(v, str) or not v.startswith(("http://", "https://")) or len(v) > 300:
        raise ValueError("must be an http(s) URL under 300 characters")
    return v


HttpUrlStr = Annotated[str | None, BeforeValidator(_check_http_url)]

_Str200 = Annotated[str, Field(max_length=200)]


class CareerProfileUpdate(BaseModel):
    """Partial update — only the fields actually sent are applied."""

    model_config = ConfigDict(extra="forbid")

    location: str | None = Field(default=None, max_length=200)
    github_url: HttpUrlStr = None
    linkedin_url: HttpUrlStr = None
    portfolio_url: HttpUrlStr = None
    preferred_roles: list[_Str200] | None = None
    preferred_locations: list[_Str200] | None = None
    work_modes: list[WorkMode] | None = None
    expected_salary_min: int | None = Field(default=None, ge=0)
    expected_salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=3)
    salary_period: SalaryPeriod | None = None
    years_experience: float | None = Field(default=None, ge=0, le=70)
    seniority: Seniority | None = None
    career_goals: str | None = Field(default=None, max_length=4000)


class CareerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    location: str | None
    github_url: str | None
    linkedin_url: str | None
    portfolio_url: str | None
    preferred_roles: list[str]
    preferred_locations: list[str]
    work_modes: list[str]
    expected_salary_min: int | None
    expected_salary_max: int | None
    salary_currency: str | None
    salary_period: str | None
    years_experience: float | None
    seniority: str | None
    career_goals: str | None
    profile_strength: int
    completeness: dict[str, bool]
    created_at: dt.datetime
    updated_at: dt.datetime


class StrengthDimensionOut(BaseModel):
    key: str
    label: str
    earned: int
    max: int  # deliberately shadows the builtin as a field name; Pydantic handles it
    hint: str
    met: bool


class StrengthOut(BaseModel):
    score: int
    completeness: dict[str, bool]
    missing: list[str]
    dimensions: list[StrengthDimensionOut]


class SkillRefOut(BaseModel):
    kind: str
    ref_id: uuid.UUID


class ProfileSkillOut(BaseModel):
    slug: str
    label: str
    category: str
    proficiency: str | None
    years: float | None
    source: str
    evidence: list[SkillRefOut]


class ReorderIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)


# --- sub-entities -----------------------------------------------------------

class _ItemOutBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_index: int
    source: Source
    created_at: dt.datetime
    updated_at: dt.datetime


class ExperienceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    employment_type: str | None = Field(default=None, max_length=40)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_current: bool = False
    location: str | None = Field(default=None, max_length=200)
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)


class ExperiencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    employment_type: str | None = Field(default=None, max_length=40)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_current: bool | None = None
    location: str | None = Field(default=None, max_length=200)
    description: str | None = None
    highlights: list[str] | None = None
    tech: list[str] | None = None


class ExperienceOut(_ItemOutBase):
    company: str
    title: str
    employment_type: str | None
    start_date: dt.date | None
    end_date: dt.date | None
    is_current: bool
    location: str | None
    description: str | None
    highlights: list[str]
    tech: list[str]


class EducationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str = Field(min_length=1, max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field: str | None = Field(default=None, max_length=200)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    grade: str | None = Field(default=None, max_length=80)


class EducationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str | None = Field(default=None, min_length=1, max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field: str | None = Field(default=None, max_length=200)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    grade: str | None = Field(default=None, max_length=80)


class EducationOut(_ItemOutBase):
    institution: str
    degree: str | None
    field: str | None
    start_date: dt.date | None
    end_date: dt.date | None
    grade: str | None


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    url: HttpUrlStr = None
    highlights: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    url: HttpUrlStr = None
    highlights: list[str] | None = None
    tech: list[str] | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class ProjectOut(_ItemOutBase):
    name: str
    description: str | None
    url: str | None
    highlights: list[str]
    tech: list[str]
    start_date: dt.date | None
    end_date: dt.date | None


class CertificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    issued_date: dt.date | None = None
    expires_date: dt.date | None = None
    credential_id: str | None = Field(default=None, max_length=200)
    url: HttpUrlStr = None


class CertificationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    issued_date: dt.date | None = None
    expires_date: dt.date | None = None
    credential_id: str | None = Field(default=None, max_length=200)
    url: HttpUrlStr = None


class CertificationOut(_ItemOutBase):
    name: str
    issuer: str | None
    issued_date: dt.date | None
    expires_date: dt.date | None
    credential_id: str | None
    url: str | None


class ProfileFullOut(CareerProfileOut):
    experiences: list[ExperienceOut]
    education: list[EducationOut]
    projects: list[ProjectOut]
    certifications: list[CertificationOut]


SUBENTITY_SCHEMAS: dict[str, tuple[type[BaseModel], type[BaseModel], type[BaseModel]]] = {
    "experiences": (ExperienceIn, ExperienceOut, ExperiencePatch),
    "education": (EducationIn, EducationOut, EducationPatch),
    "projects": (ProjectIn, ProjectOut, ProjectPatch),
    "certifications": (CertificationIn, CertificationOut, CertificationPatch),
}
