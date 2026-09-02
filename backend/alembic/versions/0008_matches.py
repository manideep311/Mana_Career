"""job_matches + match_components + skill_gaps tables

Revision ID: 0008_matches
Revises: 0007_jobs
Create Date: 2026-09-02
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008_matches"
down_revision = "0007_jobs"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "job_matches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_version_id", pg.UUID(as_uuid=True)),
        sa.Column("job_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Numeric(5, 2)),
        sa.Column("band", sa.String(16)),
        sa.Column("dimension_scores", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("strengths", pg.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("gaps", pg.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("explanation", sa.Text),
        sa.Column("explanation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("inputs_hash", sa.String(64)),
        sa.Column("scorer_version", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'scoring'")),
        sa.Column("error", sa.Text),
        sa.Column("computed_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("band is null or band in ('strong','good','partial','weak')",
                           name="job_matches_band_valid"),
        sa.CheckConstraint("status in ('scoring','ready','failed')",
                           name="job_matches_status_valid"),
    )
    op.create_index("uq_job_matches_profile", "job_matches",
                    ["user_id", "job_id", "scorer_version"], unique=True,
                    postgresql_where=sa.text("resume_version_id IS NULL"))
    op.create_index("ix_job_matches_user_score", "job_matches",
                    ["user_id", sa.text("score DESC")])
    op.create_index("ix_job_matches_job", "job_matches", ["job_id"])
    op.execute("CREATE TRIGGER trg_job_matches_set_updated_at BEFORE UPDATE ON job_matches "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "match_components",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_match_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("job_matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dimension", sa.String(20), nullable=False),
        sa.Column("raw_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("weight", sa.Numeric(4, 3), nullable=False),
        sa.Column("contribution", sa.Numeric(5, 2), nullable=False),
        sa.Column("detail", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence", pg.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "dimension in ('skill','experience','education','project','technology',"
            "'location','role','seniority','salary','semantic')",
            name="match_components_dimension_valid"),
        sa.UniqueConstraint("job_match_id", "dimension", name="uq_match_components_dimension"),
    )
    op.create_index("ix_match_components_match", "match_components", ["job_match_id"])
    op.execute(
        "CREATE TRIGGER trg_match_components_set_updated_at BEFORE UPDATE ON "
        "match_components FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "skill_gaps",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("job_match_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("job_matches.id", ondelete="CASCADE")),
        sa.Column("skill_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_slug", sa.String(120), nullable=False),
        sa.Column("skill_label", sa.String(160), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("frequency", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("rationale", sa.Text),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'open'")),
        sa.Column("addressed_by_roadmap_id", pg.UUID(as_uuid=True)),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("scope in ('job','aggregate')", name="skill_gaps_scope_valid"),
        sa.CheckConstraint("severity in ('critical','important','nice_to_have')",
                           name="skill_gaps_severity_valid"),
        sa.CheckConstraint("status in ('open','learning','closed')",
                           name="skill_gaps_status_valid"),
        sa.UniqueConstraint("job_match_id", "skill_id", name="uq_skill_gaps_job_skill"),
    )
    op.create_index("ix_skill_gaps_user_scope", "skill_gaps", ["user_id", "scope"])
    op.execute("CREATE TRIGGER trg_skill_gaps_set_updated_at BEFORE UPDATE ON skill_gaps "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_skill_gaps_set_updated_at ON skill_gaps")
    op.drop_table("skill_gaps")
    op.execute("DROP TRIGGER IF EXISTS trg_match_components_set_updated_at ON match_components")
    op.drop_table("match_components")
    op.execute("DROP TRIGGER IF EXISTS trg_job_matches_set_updated_at ON job_matches")
    op.drop_table("job_matches")
