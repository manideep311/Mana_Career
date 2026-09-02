from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_DIMENSIONS = (
    "dimension in ('skill','experience','education','project','technology',"
    "'location','role','seniority','salary','semantic')"
)


class JobMatch(Base, TimestampMixin):
    __tablename__ = "job_matches"
    __table_args__ = (
        CheckConstraint(
            "band is null or band in ('strong','good','partial','weak')",
            name="job_matches_band_valid",
        ),
        CheckConstraint(
            "status in ('scoring','ready','failed')", name="job_matches_status_valid"
        ),
        Index(
            "uq_job_matches_profile",
            "user_id", "job_id", "scorer_version",
            unique=True,
            postgresql_where=text("resume_version_id IS NULL"),
        ),
        Index("ix_job_matches_user_score", "user_id", text("score DESC")),
        Index("ix_job_matches_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK: `resume_versions` is a Phase 8 table. NULL = matched vs. the
    # user's current CareerProfile.
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[decimal.Decimal | None] = mapped_column(Numeric(5, 2))
    band: Mapped[str | None] = mapped_column(String(16))
    dimension_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    strengths: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    gaps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    explanation: Mapped[str | None] = mapped_column(Text)
    explanation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    inputs_hash: Mapped[str | None] = mapped_column(String(64))
    scorer_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'scoring'")
    )
    error: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[dt.datetime | None] = mapped_column()


class MatchComponent(Base, TimestampMixin):
    __tablename__ = "match_components"
    __table_args__ = (
        CheckConstraint(_DIMENSIONS, name="match_components_dimension_valid"),
        UniqueConstraint("job_match_id", "dimension", name="uq_match_components_dimension"),
        Index("ix_match_components_match", "job_match_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_matches.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_score: Mapped[decimal.Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    weight: Mapped[decimal.Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    contribution: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class SkillGap(Base, TimestampMixin):
    __tablename__ = "skill_gaps"
    __table_args__ = (
        CheckConstraint("scope in ('job','aggregate')", name="skill_gaps_scope_valid"),
        CheckConstraint(
            "severity in ('critical','important','nice_to_have')",
            name="skill_gaps_severity_valid",
        ),
        CheckConstraint(
            "status in ('open','learning','closed')", name="skill_gaps_status_valid"
        ),
        UniqueConstraint("job_match_id", "skill_id", name="uq_skill_gaps_job_skill"),
        Index("ix_skill_gaps_user_scope", "user_id", "scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(12), nullable=False)
    job_match_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_matches.id", ondelete="CASCADE")
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    skill_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_label: Mapped[str] = mapped_column(String(160), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'open'")
    )
    # No FK: `roadmaps` is a Phase 12 table.
    addressed_by_roadmap_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
