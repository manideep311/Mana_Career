from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class JobCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str = Field(min_length=40, max_length=40_000)


class JobPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=300)


class JobRefOut(BaseModel):
    id: uuid.UUID
    status: str


class JobSkillOut(BaseModel):
    slug: str
    label: str
    weight: float


class JobCardOut(BaseModel):
    id: uuid.UUID
    title: str | None
    company: str | None
    location: str | None
    work_mode: str | None
    seniority: str | None
    employment_type: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: str | None
    is_seed: bool
    status: str
    posted_at: dt.datetime | None
    created_at: dt.datetime
    required_skills: list[JobSkillOut]


class JobDetailOut(JobCardOut):
    company_domain: str | None
    experience_min_years: int | None
    experience_max_years: int | None
    description: str | None
    responsibilities: list[str]
    preferred_skills: list[JobSkillOut]
    raw_text: str


class JobListOut(BaseModel):
    items: list[JobCardOut]
    total: int
    limit: int
    offset: int
