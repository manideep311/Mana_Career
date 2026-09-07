from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.api.v1.schemas.skill_gaps import SkillGapOut


class SkillMention(BaseModel):
    skill_slug: str
    skill_label: str
    detail: str | None


class NextStep(BaseModel):
    kind: str
    title: str
    reason: str
    entity_type: str | None
    entity_id: uuid.UUID | None


class RoadmapSummary(BaseModel):
    id: uuid.UUID
    title: str
    next_step: str | None
    milestones_done: int
    milestones_total: int


class InsightsOut(BaseModel):
    strengths: list[SkillMention]
    skills_to_develop: list[SkillGapOut]
    recommended_next_step: NextStep | None
    trending_skills: list[SkillMention]
    suggested_projects: list[str]
    roadmap_summary: RoadmapSummary | None
