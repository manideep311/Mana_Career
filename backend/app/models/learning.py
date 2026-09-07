from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LearningResource(Base, TimestampMixin):
    __tablename__ = "learning_resources"
    __table_args__ = (
        CheckConstraint(
            "type in ('course','book','doc','video','article','project')",
            name="learning_resources_type_valid",
        ),
        CheckConstraint(
            "level in ('beginner','intermediate','advanced')",
            name="learning_resources_level_valid",
        ),
        CheckConstraint(
            "cost in ('free','paid','freemium')", name="learning_resources_cost_valid"
        ),
        Index(
            "ix_learning_resources_embedding", "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_learning_resources_skills", "skills", postgresql_using="gin"),
        Index("ix_learning_resources_level", "level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(12), nullable=False)
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    est_hours: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[str] = mapped_column(String(10), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # The literal dim must stay in sync with app/core/config.py `embed_dim`
    # (default 1024) and the migration's Vector(1024).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    is_active: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("true")
    )


class LearningRecommendation(Base, TimestampMixin):
    __tablename__ = "learning_recommendations"
    __table_args__ = (
        CheckConstraint(
            "scope in ('aggregate','job')", name="learning_recommendations_scope_valid"
        ),
        CheckConstraint(
            "status in ('planning','active','archived')",
            name="learning_recommendations_status_valid",
        ),
        Index("ix_learning_recommendations_user", "user_id", text("created_at DESC")),
        Index("ix_learning_recommendations_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(12), nullable=False)
    # No FK: `jobs` rows can be seed rows the user doesn't own; loose reference.
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    summary: Mapped[str | None] = mapped_column(Text)
    next_step: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'planning'")
    )
    generation_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class RoadmapMilestone(Base, TimestampMixin):
    __tablename__ = "roadmap_milestones"
    __table_args__ = (
        CheckConstraint(
            "status in ('not_started','in_progress','done')",
            name="roadmap_milestones_status_valid",
        ),
        Index("ix_roadmap_milestones_rec", "recommendation_id", "order_index"),
        Index("ix_roadmap_milestones_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # No FK: skills come from the taxonomy; loose reference.
    skill_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    skill_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_label: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    resource_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'")
    )
    est_hours: Mapped[int | None] = mapped_column(Integer)
    practice_project: Mapped[str | None] = mapped_column(Text)
    checkpoint: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'not_started'")
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column()
