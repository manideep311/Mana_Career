from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class SkillGapOut(BaseModel):
    # Mapped explicitly by `_gap_out` — no `from_attributes`.
    id: uuid.UUID
    scope: str
    job_match_id: uuid.UUID | None
    skill_slug: str
    skill_label: str
    severity: str
    frequency: int
    rationale: str | None
    status: str


class SkillGapPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^(open|learning|closed)$")
