from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class EvalRun(Base, TimestampMixin):
    __tablename__ = "eval_runs"
    __table_args__ = (
        CheckConstraint(
            "suite in ('retrieval','generation','matching')",
            name="eval_runs_suite_valid",
        ),
        CheckConstraint(
            "status in ('running','passed','failed','error')",
            name="eval_runs_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    suite: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    git_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'running'")
    )
    started_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class EvalResult(Base, TimestampMixin):
    __tablename__ = "eval_results"
    __table_args__ = (Index("ix_eval_results_run", "eval_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(80), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    expected: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    actual: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    judge_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
