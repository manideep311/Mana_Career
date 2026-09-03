from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class EvalRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite: Literal["retrieval"]


class EvalRunOut(BaseModel):
    # Mapped explicitly by `_run_out` — no `from_attributes`.
    id: uuid.UUID
    suite: str
    dataset_version: str
    git_sha: str
    provider: str
    model_ids: dict[str, Any]
    metrics: dict[str, Any]
    status: str
    started_at: dt.datetime
    ended_at: dt.datetime | None


class EvalRunListOut(BaseModel):
    items: list[EvalRunOut]
    total: int


class EvalResultOut(BaseModel):
    # Mapped explicitly by `_result_out` — no `from_attributes`.
    id: uuid.UUID
    case_id: str
    scores: dict[str, Any]
    passed: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
