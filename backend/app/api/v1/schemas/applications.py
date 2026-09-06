from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApplicationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID
    intent: Literal["prepare", "save"] = "prepare"


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    resume_version_id: uuid.UUID | None
    cover_letter_id: uuid.UUID | None
    application_email_id: uuid.UUID | None
    status: str
    match_score: Decimal | None
    source: str
    notes: str | None
    ai_session_id: uuid.UUID | None
    applied_at: dt.datetime | None
    last_status_change_at: dt.datetime
    created_at: dt.datetime
    updated_at: dt.datetime


class ApplicationPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["saved", "applied", "interview", "offer", "rejected", "withdrawn"] | None = None
    notes: str | None = None


class ApplicationNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)


class ApplicationListOut(BaseModel):
    items: list[ApplicationOut]
    total: int
    limit: int
    offset: int


class TimelineItemOut(BaseModel):
    kind: str
    at: dt.datetime
    title: str
    detail: dict[str, Any]


class ApplicationTimelineOut(BaseModel):
    items: list[TimelineItemOut]
