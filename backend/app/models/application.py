from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CoverLetter(Base, TimestampMixin):
    __tablename__ = "cover_letters"
    __table_args__ = (
        CheckConstraint(
            "created_by in ('user','mana_ai')", name="cover_letters_created_by_valid"
        ),
        Index("ix_cover_letters_user", "user_id", text("created_at DESC")),
        Index("ix_cover_letters_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK on job_id/application_id/resume_version_id/supersedes_id: loose optional
    # cross-references, mirroring the resume_versions precedent (migration 0011).
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tone: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'professional'")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    rendered_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    generation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'mana_ai'")
    )


class ApplicationEmail(Base, TimestampMixin):
    __tablename__ = "application_emails"
    __table_args__ = (
        CheckConstraint(
            "body_format in ('plain','html')", name="application_emails_body_format_valid"
        ),
        CheckConstraint(
            "status in "
            "('draft','awaiting_approval','approved','sending','sent','failed','canceled')",
            name="application_emails_status_valid",
        ),
        Index("ix_application_emails_user", "user_id", text("created_at DESC")),
        Index("ix_application_emails_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # to_email/to_name/provider nullable: a draft has no recipient/provider yet
    # (Phase 9 has no recipient-inference or send capability -- Phase 10's
    # review step is where a human fills these in before approval).
    to_email: Mapped[str | None] = mapped_column(String(320))
    to_name: Mapped[str | None] = mapped_column(String(200))
    cc: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    bcc: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_format: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'plain'")
    )
    attachment_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'draft'")
    )
    provider: Mapped[str | None] = mapped_column(String(16))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    send_error: Mapped[str | None] = mapped_column(Text)
    generation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status in ('saved','preparing','awaiting_approval','applied',"
            "'interview','offer','rejected','withdrawn')",
            name="applications_status_valid",
        ),
        CheckConstraint("source in ('user','mana_ai')", name="applications_source_valid"),
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_user_updated", "user_id", text("updated_at DESC")),
        Index("ix_applications_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK on job_id/resume_version_id/cover_letter_id/application_email_id/
    # ai_session_id: loose optional cross-references, matching every other
    # forward reference in this schema (resume_versions.application_id, etc.).
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cover_letter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    application_email_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'preparing'")
    )
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'mana_ai'")
    )
    ai_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    applied_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_status_change_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "action_type in ('send_application_email')",
            name="approval_requests_action_type_valid",
        ),
        CheckConstraint(
            "status in ('pending','approved','rejected','superseded','expired')",
            name="approval_requests_status_valid",
        ),
        Index("ix_approval_requests_user_status", "user_id", "status"),
        Index(
            "uq_approval_requests_run_pending",
            "run_id", "action_type",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK on application_id/ai_session_id/decided_by -- same loose-reference
    # convention as Application above.
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ai_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'send_application_email'")
    )
    payload_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
