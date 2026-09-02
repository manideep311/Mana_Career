from __future__ import annotations

import decimal
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    __table_args__ = (
        Index("ix_skills_aliases", "aliases", postgresql_using="gin"),
        Index(
            "ix_skills_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    # The literal dim must stay in sync with app/core/config.py `embed_dim`
    # (default 1024) and the migration's Vector(1024).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))


class ProfileSkill(Base, TimestampMixin):
    __tablename__ = "profile_skills"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "skill_id", name="uq_profile_skills_profile_skill"
        ),
        CheckConstraint(
            "proficiency in ('beginner','intermediate','advanced','expert')",
            name="profile_skills_proficiency_valid",
        ),
        CheckConstraint(
            "source in ('user','resume_extraction','inferred')",
            name="profile_skills_source_valid",
        ),
        Index("ix_profile_skills_profile", "profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("career_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    proficiency: Mapped[str | None] = mapped_column(String(16))
    years: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 1))
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'resume_extraction'")
    )
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
