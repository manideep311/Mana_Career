from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["chat", "agent_run"] = "chat"
    context: dict[str, Any] | None = None


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)


class GoalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: Literal[
        "understand_job", "enrich_job", "analyze_profile", "prepare_application"
    ]
    inputs: dict[str, Any] = Field(default_factory=dict)


class MessageOut(BaseModel):
    # Mapped explicitly by `_message_out` — no `from_attributes`.
    id: uuid.UUID
    role: str
    content: str
    blocks: list[dict[str, Any]]
    created_at: dt.datetime


class SessionSummaryOut(BaseModel):
    # Mapped explicitly by `_session_summary_out` — no `from_attributes`.
    id: uuid.UUID
    kind: str
    goal: str | None
    title: str | None
    status: str
    run_id: str | None
    totals: dict[str, Any]
    error: str | None
    created_at: dt.datetime
    started_at: dt.datetime | None
    ended_at: dt.datetime | None


class SessionOut(SessionSummaryOut):
    messages: list[MessageOut]


class SessionListOut(BaseModel):
    items: list[SessionSummaryOut]
    total: int


class AiActionOut(BaseModel):
    # Mapped explicitly by `_action_out` — no `from_attributes`.
    id: uuid.UUID
    ai_session_id: uuid.UUID | None
    run_id: str | None
    node: str
    action_key: str
    summary: str
    status: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    occurred_at: dt.datetime


class AiActionListOut(BaseModel):
    items: list[AiActionOut]
    total: int


class RunRefOut(BaseModel):
    run_id: str
