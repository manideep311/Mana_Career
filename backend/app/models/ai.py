from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_SESSION_STATUS = (
    "status in ('idle','running','awaiting_approval','completed',"
    "'rejected','halted','error')"
)
_STEP_STATUS = (
    "status in ('ok','deduped','skipped_fresh','error','budget_exceeded')"
)


class AiSession(Base, TimestampMixin):
    __tablename__ = "ai_sessions"
    __table_args__ = (
        CheckConstraint(
            "kind in ('chat','agent_run')", name="ai_sessions_kind_valid"
        ),
        CheckConstraint(_SESSION_STATUS, name="ai_sessions_status_valid"),
        Index("ix_ai_sessions_user", "user_id", text("created_at DESC")),
        Index("ix_ai_sessions_status", "status"),
        Index("ix_ai_sessions_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    goal: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(200))
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'idle'")
    )
    run_id: Mapped[str | None] = mapped_column(String(64))
    run_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    budget: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    totals: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role in ('user','assistant','tool','system')",
            name="messages_role_valid",
        ),
        Index("ix_messages_session", "ai_session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ai_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    tool_call_id: Mapped[str | None] = mapped_column(String(64))
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    token_usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    model_id: Mapped[str | None] = mapped_column(String(80))
    provider: Mapped[str | None] = mapped_column(String(32))


class AiAction(Base, TimestampMixin):
    __tablename__ = "ai_actions"
    __table_args__ = (
        CheckConstraint(
            "status in ('ok','warning','error')", name="ai_actions_status_valid"
        ),
        Index("ix_ai_actions_user", "user_id", text("occurred_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK: an action may be logged before its session row is committed.
    ai_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    run_id: Mapped[str | None] = mapped_column(String(64))
    node: Mapped[str] = mapped_column(String(40), nullable=False)
    action_key: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'ok'")
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[decimal.Decimal | None] = mapped_column(Numeric(8, 4))
    occurred_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class AgentStep(Base, TimestampMixin):
    __tablename__ = "agent_steps"
    __table_args__ = (
        CheckConstraint(_STEP_STATUS, name="agent_steps_status_valid"),
        Index("ix_agent_steps_run", "run_id", "step_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ai_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    node: Mapped[str] = mapped_column(String(40), nullable=False)
    input_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    output_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    llm_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    tool_calls: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    tokens_in: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost_usd: Mapped[decimal.Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
