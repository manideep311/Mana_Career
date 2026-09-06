from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApprovalDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    note: str | None = None


class ApprovalRequestOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    action_type: str
    payload_snapshot: dict[str, Any]
    status: str
    decided_at: dt.datetime | None
    decision_note: str | None
    created_at: dt.datetime


class ApprovalRequestListOut(BaseModel):
    items: list[ApprovalRequestOut]
