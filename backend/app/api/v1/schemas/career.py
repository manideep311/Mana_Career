from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _FromAttrs(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PathSkillOut(_FromAttrs):
    slug: str
    label: str
    demand: float
    required: bool
    have: bool
    evidence: list[str]


class PathActionOut(_FromAttrs):
    kind: Literal["project", "resume", "apply", "roadmap", "explore"]
    title: str
    detail: str


class RelatedPathOut(BaseModel):
    slug: str
    title: str


class PathJobOut(BaseModel):
    id: uuid.UUID
    title: str
    company: str | None


class CareerPathOut(BaseModel):
    slug: str
    title: str
    summary: str
    job_count: int
    stated_target: bool
    fit: Literal["close", "stretch", "pivot"]
    fit_label: str
    fit_explanation: str
    why: str
    have: list[PathSkillOut]
    missing: list[PathSkillOut]
    relevant_experience: list[str]
    seniority_note: str | None
    next_actions: list[PathActionOut]
    related: list[RelatedPathOut]
    roles: list[PathJobOut]
    evidence_is_thin: bool


class CareerPathsOut(BaseModel):
    paths: list[CareerPathOut]
    notes: list[str]


class ResourceOut(_FromAttrs):
    id: uuid.UUID
    title: str
    provider: str
    url: str
    type: str
    level: str
    est_hours: int | None
    cost: str


class SkillStepOut(_FromAttrs):
    slug: str
    label: str
    category: str
    why_it_matters: str
    requirement: str
    current_evidence: str
    resource: ResourceOut | None
    practice_project: str
    roadmap_position: int | None


class SkillPlanOut(BaseModel):
    path_slug: str | None
    path_title: str | None
    steps: list[SkillStepOut]


class NextActionOut(_FromAttrs):
    kind: str
    title: str
    detail: str
    href: str | None


class JourneyStageOut(_FromAttrs):
    key: str
    label: str
    status: Literal["done", "current", "upcoming"]
    detail: str


class MilestoneBriefOut(_FromAttrs):
    id: uuid.UUID
    title: str
    skill_label: str
    status: str


class RoadmapBriefOut(_FromAttrs):
    id: uuid.UUID
    title: str
    done: int
    total: int
    current: MilestoneBriefOut | None
    upcoming: MilestoneBriefOut | None


class OpportunityOut(_FromAttrs):
    job_id: uuid.UUID
    title: str
    company: str | None
    band: str | None
    reason: str | None
    gap: str | None


class CareerOverviewOut(BaseModel):
    direction: CareerPathOut | None
    direction_summary: str
    next_actions: list[NextActionOut]
    journey: list[JourneyStageOut]
    roadmap: RoadmapBriefOut | None
    opportunities: list[OpportunityOut]
    skills: list[SkillStepOut]
    notes: list[str]
    has_resume: bool


class AnalysisIssueOut(_FromAttrs):
    id: str
    severity: Literal["high", "medium", "low"]
    area: str
    problem: str
    why_it_matters: str
    suggestion: str
    examples: list[str]


class SkillEvidenceOut(_FromAttrs):
    slug: str
    label: str
    category: str
    applied: bool
    lines: list[str]


class RoleAlignmentOut(_FromAttrs):
    target: str
    evidenced: list[str]
    missing: list[str]


class ResumeAnalysisOut(BaseModel):
    resume_id: uuid.UUID
    enough_text: bool
    sections: dict[str, bool]
    word_count: int
    page_count: int | None
    bullet_count: int
    bullets_with_results: int
    strengths: list[str]
    issues: list[AnalysisIssueOut]
    skills: list[SkillEvidenceOut]
    alignment: RoleAlignmentOut | None
    target_path: RelatedPathOut | None
