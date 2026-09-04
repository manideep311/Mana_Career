from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ResumeVersion(Base, TimestampMixin):
    __tablename__ = "resume_versions"
    __table_args__ = (
        CheckConstraint(
            "kind in ('base_snapshot','manual_edit','ai_tailored')",
            name="resume_versions_kind_valid",
        ),
        CheckConstraint(
            "created_by in ('user','mana_ai')",
            name="resume_versions_created_by_valid",
        ),
        Index("ix_resume_versions_resume", "resume_id", text("created_at DESC")),
        Index("ix_resume_versions_user", "user_id"),
        Index("ix_resume_versions_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    # No FK: a version may reference a job/application/parent without enforcing referential
    # integrity here (mirrors the ai_actions.entity_id / job_chunks.owner_id precedent).
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    label: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    rendered_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    generation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'user'")
    )


class ResumeChunk(Base, TimestampMixin):
    __tablename__ = "resume_chunks"
    __table_args__ = (
        Index("ix_resume_chunks_version", "resume_version_id", "chunk_index"),
        Index("ix_resume_chunks_content_tsv", "content_tsv", postgresql_using="gin"),
        Index(
            "ix_resume_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # No FK: mirrors job_chunks.owner_id — denormalized for ownership checks without a join.
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(40), nullable=False)
    ref_id: Mapped[str | None] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    embed_model: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default=text("'fake-embed-1'")
    )
    embed_dim: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1024")
    )
    # The literal dim must stay in sync with app/core/config.py `embed_dim` and the migration.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )


class ResumeSuggestion(Base, TimestampMixin):
    __tablename__ = "resume_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status in ('open','accepted','edited','dismissed')",
            name="resume_suggestions_status_valid",
        ),
        Index("ix_resume_suggestions_user", "user_id", text("created_at DESC")),
        Index("ix_resume_suggestions_version", "resume_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section: Mapped[str] = mapped_column(String(40), nullable=False)
    target_ref_id: Mapped[str | None] = mapped_column(String(80))
    suggestion_type: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_change: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'open'")
    )
    # No FK: set only once a suggestion is accepted/edited into a new version.
    resulting_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'mana_ai'")
    )
    generation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
