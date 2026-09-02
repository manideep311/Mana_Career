from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# `'english'::regconfig` (an explicit regconfig constant), NOT a bare string:
# `to_tsvector(text, text)` is only STABLE, so a bare 'english' makes the whole
# expression non-IMMUTABLE and Postgres rejects it in a STORED generated column.
_TSV_EXPR = (
    "to_tsvector('english'::regconfig, "
    "coalesce(title,'') || ' ' || coalesce(company,'') || ' ' || "
    "coalesce(description,'') || ' ' || array_to_string(responsibilities, ' '))"
)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("source in ('user_paste','user_upload','seed')", name="jobs_source_valid"),
        CheckConstraint(
            "work_mode is null or work_mode in ('remote','hybrid','onsite')",
            name="jobs_work_mode_valid",
        ),
        CheckConstraint(
            "seniority is null or seniority in "
            "('intern','junior','mid','senior','staff','principal','lead','manager')",
            name="jobs_seniority_valid",
        ),
        CheckConstraint(
            "salary_period is null or salary_period in ('year','month','day','hour')",
            name="jobs_salary_period_valid",
        ),
        CheckConstraint(
            "salary_source is null or salary_source in ('jd','estimate')",
            name="jobs_salary_source_valid",
        ),
        CheckConstraint("status in ('ingesting','ready','failed')", name="jobs_status_valid"),
        Index("ix_jobs_user_id", "user_id"),
        Index("ix_jobs_is_seed", "is_seed"),
        Index("ix_jobs_seniority", "seniority"),
        Index("ix_jobs_work_mode", "work_mode"),
        Index("ix_jobs_created_at", text("created_at DESC")),
        Index("ix_jobs_structured", "structured", postgresql_using="gin"),
        Index("ix_jobs_required_skills", "required_skills", postgresql_using="gin",
              postgresql_ops={"required_skills": "jsonb_path_ops"}),
        Index("ix_jobs_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_jobs_title_trgm", "title", postgresql_using="gin",
              postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_jobs_company_trgm", "company", postgresql_using="gin",
              postgresql_ops={"company": "gin_trgm_ops"}),
        # Stable upsert key for the seed loader (Task 7): one seed row per source_ref.
        Index("uq_jobs_seed_source_ref", "source_ref", unique=True,
              postgresql_where=text("is_seed")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    is_seed: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'user_paste'")
    )
    source_ref: Mapped[str | None] = mapped_column(String(300))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200))
    company_domain: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    work_mode: Mapped[str | None] = mapped_column(String(16))
    employment_type: Mapped[str | None] = mapped_column(String(40))
    seniority: Mapped[str | None] = mapped_column(String(20))
    experience_min_years: Mapped[int | None] = mapped_column(Integer)
    experience_max_years: Mapped[int | None] = mapped_column(Integer)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(10))
    salary_source: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    required_skills: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    preferred_skills: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    structured: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    extraction_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ingesting'")
    )
    ingest_error: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[dt.datetime | None] = mapped_column()
    deleted_at: Mapped[dt.datetime | None] = mapped_column()
    # Read-only: Postgres maintains this from title/company/description/responsibilities.
    search_tsv: Mapped[str] = mapped_column(TSVECTOR, Computed(_TSV_EXPR, persisted=True))


class JobChunk(Base, TimestampMixin):
    __tablename__ = "job_chunks"
    __table_args__ = (
        UniqueConstraint("job_id", "chunk_index", name="uq_job_chunks_job_chunk"),
        CheckConstraint(
            "section in ('description','responsibilities','requirements')",
            name="job_chunks_section_valid",
        ),
        Index("ix_job_chunks_job_id", "job_id"),
        Index("ix_job_chunks_chunk_tsv", "chunk_tsv", postgresql_using="gin"),
        Index(
            "ix_job_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embed_model: Mapped[str] = mapped_column(String(60), nullable=False)
    embed_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    # The literal dim must stay in sync with app/core/config.py `embed_dim` and the migration.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    chunk_tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english'::regconfig, content)", persisted=True)
    )
