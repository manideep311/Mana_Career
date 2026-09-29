from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RoadmapCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(default="aggregate", pattern=r"^(aggregate|job)$")
    job_id: uuid.UUID | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class RoadmapRefOut(BaseModel):
    id: uuid.UUID


class RoadmapOut(BaseModel):
    id: uuid.UUID
    scope: str
    job_id: uuid.UUID | None
    title: str
    summary: str | None
    next_step: str | None
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class MilestoneOut(BaseModel):
    id: uuid.UUID
    order_index: int
    skill_slug: str
    skill_label: str
    title: str
    why_it_matters: str
    resource_ids: list[uuid.UUID]
    est_hours: int | None
    practice_project: str | None
    checkpoint: str | None
    status: str
    completed_at: dt.datetime | None
    # Where it sits on the timeline; only set on the full roadmap view.
    phase: Literal["done", "current", "next_30", "next_60_90", "later"] | None = None


class RoadmapDetailOut(RoadmapOut):
    milestones: list[MilestoneOut]
    # The weekly pace the phases assume, so the UI can say so.
    hours_per_week: int


class RoadmapListOut(BaseModel):
    items: list[RoadmapOut]


class RoadmapPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^(active|archived)$")


class MilestonePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^(not_started|in_progress|done)$")
