from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.resume.extractor import ResumeExtraction


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str | None
    original_filename: str | None
    content_type: str
    size_bytes: int
    page_count: int | None
    status: str
    parse_error: str | None
    is_primary: bool
    confirmed_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


class ResumePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    is_primary: bool | None = None


class ConfirmProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extraction: ResumeExtraction


class TailorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID


class ResumeVersionOut(BaseModel):
    id: uuid.UUID
    kind: str
    label: str | None
    job_id: uuid.UUID | None
    parent_version_id: uuid.UUID | None
    created_by: str
    created_at: dt.datetime
    claim_validation: dict[str, Any]


class ResumeVersionListOut(BaseModel):
    items: list[ResumeVersionOut]


class ResumeVersionDetailOut(ResumeVersionOut):
    content: dict[str, Any]


class FieldDeltaOut(BaseModel):
    path: str
    op: str
    before: Any
    after: Any


class ResumeDiffOut(BaseModel):
    deltas: list[FieldDeltaOut]
