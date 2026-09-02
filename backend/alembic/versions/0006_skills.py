"""skills taxonomy + profile_skills tables

Revision ID: 0006_skills
Revises: 0005_resumes
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0006_skills"
down_revision = "0005_resumes"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(120), unique=True, nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("aliases", sa.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("embedding", Vector(1024)),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
    )
    op.create_index("ix_skills_aliases", "skills", ["aliases"], postgresql_using="gin")
    op.create_index(
        "ix_skills_embedding",
        "skills",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.execute(
        "CREATE TRIGGER trg_skills_set_updated_at BEFORE UPDATE ON skills "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "profile_skills",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proficiency", sa.String(16)),
        sa.Column("years", sa.Numeric(4, 1)),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'resume_extraction'"),
        ),
        sa.Column("evidence_refs", pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.UniqueConstraint("profile_id", "skill_id", name="uq_profile_skills_profile_skill"),
        sa.CheckConstraint(
            "proficiency in ('beginner','intermediate','advanced','expert')",
            name="profile_skills_proficiency_valid",
        ),
        sa.CheckConstraint(
            "source in ('user','resume_extraction','inferred')",
            name="profile_skills_source_valid",
        ),
    )
    op.create_index("ix_profile_skills_profile", "profile_skills", ["profile_id"])
    op.execute(
        "CREATE TRIGGER trg_profile_skills_set_updated_at BEFORE UPDATE ON profile_skills "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_profile_skills_set_updated_at ON profile_skills")
    op.drop_table("profile_skills")
    op.execute("DROP TRIGGER IF EXISTS trg_skills_set_updated_at ON skills")
    op.drop_table("skills")
