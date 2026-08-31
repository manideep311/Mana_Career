from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
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

_SENIORITY = "seniority in ('junior','mid','senior','staff','lead','principal')"
_SALARY_PERIOD = "salary_period in ('year','month')"
_SOURCE = "source in ('user','resume_extraction')"


class CareerProfile(Base, TimestampMixin):
    __tablename__ = "career_profiles"
    __table_args__ = (
        CheckConstraint(_SENIORITY, name="career_profile_seniority_valid"),
        CheckConstraint(_SALARY_PERIOD, name="career_profile_salary_period_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    location: Mapped[str | None] = mapped_column(String(200))
    github_url: Mapped[str | None] = mapped_column(String(300))
    linkedin_url: Mapped[str | None] = mapped_column(String(300))
    portfolio_url: Mapped[str | None] = mapped_column(String(300))
    preferred_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    preferred_locations: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    work_modes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    expected_salary_min: Mapped[int | None] = mapped_column(Integer)
    expected_salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(8))
    years_experience: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 1))
    seniority: Mapped[str | None] = mapped_column(String(16))
    career_goals: Mapped[str | None] = mapped_column(Text)
    profile_strength: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completeness: Mapped[dict[str, bool]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class _SubEntity(TimestampMixin):
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("career_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'user'")
    )
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class ProfileExperience(_SubEntity, Base):
    __tablename__ = "profile_experiences"
    __table_args__ = (
        CheckConstraint(_SOURCE, name="profile_experience_source_valid"),
        Index("ix_profile_experiences_profile_id", "profile_id"),
    )
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(40))
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    location: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    highlights: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    tech: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )


class ProfileEducation(_SubEntity, Base):
    __tablename__ = "profile_education"
    __table_args__ = (
        CheckConstraint(_SOURCE, name="profile_education_source_valid"),
        Index("ix_profile_education_profile_id", "profile_id"),
    )
    institution: Mapped[str] = mapped_column(String(200), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(200))
    field: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    grade: Mapped[str | None] = mapped_column(String(80))


class ProfileProject(_SubEntity, Base):
    __tablename__ = "profile_projects"
    __table_args__ = (
        CheckConstraint(_SOURCE, name="profile_project_source_valid"),
        Index("ix_profile_projects_profile_id", "profile_id"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(300))
    highlights: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    tech: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)


class ProfileCertification(_SubEntity, Base):
    __tablename__ = "profile_certifications"
    __table_args__ = (
        CheckConstraint(_SOURCE, name="profile_certification_source_valid"),
        Index("ix_profile_certifications_profile_id", "profile_id"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(200))
    issued_date: Mapped[dt.date | None] = mapped_column(Date)
    expires_date: Mapped[dt.date | None] = mapped_column(Date)
    credential_id: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(300))
