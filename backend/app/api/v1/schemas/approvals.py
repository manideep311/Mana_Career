from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApprovalDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    note: str | None = None
    # Who the approved email goes to. Required to approve: the approval then
    # covers the address too (the server validates and re-hashes it).
    to_email: str | None = Field(default=None, max_length=320)
    to_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _approve_needs_a_recipient(self) -> Self:
        if self.decision == "approve" and not (self.to_email or "").strip():
            raise ValueError("to_email is required to approve and send")
        return self


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
