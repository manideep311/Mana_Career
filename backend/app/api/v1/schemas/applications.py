from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ApplicationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    resume_version_id: uuid.UUID | None
    cover_letter_id: uuid.UUID | None
    application_email_id: uuid.UUID | None
    status: str
    match_score: Decimal | None
    source: str
    applied_at: dt.datetime | None
    last_status_change_at: dt.datetime
    created_at: dt.datetime
    updated_at: dt.datetime
