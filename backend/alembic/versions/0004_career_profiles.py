"""career_profiles and sub-entities

Revision ID: 0004_career_profiles
Revises: 0003_users
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004_career_profiles"
down_revision = "0003_users"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")
_ARR = pg.ARRAY(sa.Text())
_EMPTY = sa.text("'{}'")


def _common() -> list[sa.Column]:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'user'")),
        sa.Column("order_index", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
    ]


def upgrade() -> None:
    op.create_table(
        "career_profiles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location", sa.String(200)),
        sa.Column("github_url", sa.String(300)),
        sa.Column("linkedin_url", sa.String(300)),
        sa.Column("portfolio_url", sa.String(300)),
        sa.Column("preferred_roles", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("preferred_locations", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("work_modes", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("expected_salary_min", sa.Integer),
        sa.Column("expected_salary_max", sa.Integer),
        sa.Column("salary_currency", sa.String(3)),
        sa.Column("salary_period", sa.String(8)),
        sa.Column("years_experience", sa.Numeric(4, 1)),
        sa.Column("seniority", sa.String(16)),
        sa.Column("career_goals", sa.Text),
        sa.Column("profile_strength", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("completeness", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.UniqueConstraint("user_id", name="uq_career_profiles_user_id"),
        sa.CheckConstraint(
            "seniority in ('junior','mid','senior','staff','lead','principal')",
            name="career_profile_seniority_valid",
        ),
        sa.CheckConstraint("salary_period in ('year','month')",
                           name="career_profile_salary_period_valid"),
    )

    experiences_extra = [
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("employment_type", sa.String(40)),
        sa.Column("start_date", sa.Date), sa.Column("end_date", sa.Date),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("location", sa.String(200)),
        sa.Column("description", sa.Text),
        sa.Column("highlights", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("tech", _ARR, nullable=False, server_default=_EMPTY),
    ]
    education_extra = [
        sa.Column("institution", sa.String(200), nullable=False),
        sa.Column("degree", sa.String(200)), sa.Column("field", sa.String(200)),
        sa.Column("start_date", sa.Date), sa.Column("end_date", sa.Date),
        sa.Column("grade", sa.String(80)),
    ]
    projects_extra = [
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text), sa.Column("url", sa.String(300)),
        sa.Column("highlights", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("tech", _ARR, nullable=False, server_default=_EMPTY),
        sa.Column("start_date", sa.Date), sa.Column("end_date", sa.Date),
    ]
    certifications_extra = [
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("issuer", sa.String(200)),
        sa.Column("issued_date", sa.Date), sa.Column("expires_date", sa.Date),
        sa.Column("credential_id", sa.String(200)), sa.Column("url", sa.String(300)),
    ]
    tables = [
        ("profile_experiences", "profile_experience", experiences_extra),
        ("profile_education", "profile_education", education_extra),
        ("profile_projects", "profile_project", projects_extra),
        ("profile_certifications", "profile_certification", certifications_extra),
    ]
    for tbl, singular, extra in tables:
        op.create_table(
            tbl, *_common(), *extra,
            sa.CheckConstraint("source in ('user','resume_extraction')",
                               name=f"{singular}_source_valid"),
        )
        op.create_index(f"ix_{tbl}_profile_id", tbl, ["profile_id"])

    for tbl in ("career_profiles", "profile_experiences", "profile_education",
                "profile_projects", "profile_certifications"):
        op.execute(
            f"CREATE TRIGGER trg_{tbl}_set_updated_at BEFORE UPDATE ON {tbl} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for tbl in ("profile_certifications", "profile_projects", "profile_education",
                "profile_experiences", "career_profiles"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tbl}_set_updated_at ON {tbl}")
        op.drop_table(tbl)
