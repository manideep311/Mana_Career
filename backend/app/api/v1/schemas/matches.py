from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MatchCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID


class RecomputeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # "all" (every visible ready job) or one canonical job UUID string. The
    # shape is a real UUID so a malformed scope is a 422, not a route-level
    # ValueError from uuid.UUID(...).
    scope: str = Field(
        pattern=(
            r"^(all|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
        )
    )


class MatchRefOut(BaseModel):
    id: uuid.UUID
    status: str


class MatchDimOut(BaseModel):
    dimension: str
    raw_score: float
    weight: float
    contribution: float


class MatchComponentOut(MatchDimOut):
    detail: dict[str, Any]
    evidence: list[dict[str, Any]]


class MatchOut(BaseModel):
    # Mapped explicitly by `_match_out` — no `from_attributes`.
    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    score: float | None
    band: str | None
    dimension_scores: dict[str, float]
    strengths: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    explanation: str | None
    computed_at: dt.datetime | None


class MatchListOut(BaseModel):
    items: list[MatchOut]
