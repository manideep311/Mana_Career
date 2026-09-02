"""jobs + job_chunks tables

Revision ID: 0007_jobs
Revises: 0006_skills
Create Date: 2026-09-02
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0007_jobs"
down_revision = "0006_skills"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")
# `'english'::regconfig` (explicit regconfig constant): a bare 'english' string
# leaves `to_tsvector` only STABLE, which a STORED generated column rejects.
_TSV_EXPR = (
    "to_tsvector('english'::regconfig, "
    "coalesce(title,'') || ' ' || coalesce(company,'') || ' ' || "
    "coalesce(description,'') || ' ' || array_to_string(responsibilities, ' '))"
)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("is_seed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'user_paste'")),
        sa.Column("source_ref", sa.String(300)),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("title", sa.String(300)),
        sa.Column("company", sa.String(200)),
        sa.Column("company_domain", sa.String(200)),
        sa.Column("location", sa.String(200)),
        sa.Column("work_mode", sa.String(16)),
        sa.Column("employment_type", sa.String(40)),
        sa.Column("seniority", sa.String(20)),
        sa.Column("experience_min_years", sa.Integer),
        sa.Column("experience_max_years", sa.Integer),
        sa.Column("salary_min", sa.Integer),
        sa.Column("salary_max", sa.Integer),
        sa.Column("salary_currency", sa.String(3)),
        sa.Column("salary_period", sa.String(10)),
        sa.Column("salary_source", sa.String(16)),
        sa.Column("description", sa.Text),
        sa.Column(
            "responsibilities", sa.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "required_skills", pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "preferred_skills", pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "structured", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "extraction_meta", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'ingesting'")),
        sa.Column("ingest_error", sa.Text),
        sa.Column("posted_at", _TS),
        sa.Column("deleted_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("search_tsv", pg.TSVECTOR, sa.Computed(_TSV_EXPR, persisted=True)),
        sa.CheckConstraint(
            "source in ('user_paste','user_upload','seed')", name="jobs_source_valid"
        ),
        sa.CheckConstraint(
            "work_mode is null or work_mode in ('remote','hybrid','onsite')",
            name="jobs_work_mode_valid",
        ),
        sa.CheckConstraint(
            "seniority is null or seniority in "
            "('intern','junior','mid','senior','staff','principal','lead','manager')",
            name="jobs_seniority_valid",
        ),
        sa.CheckConstraint(
            "salary_period is null or salary_period in ('year','month','day','hour')",
            name="jobs_salary_period_valid",
        ),
        sa.CheckConstraint(
            "salary_source is null or salary_source in ('jd','estimate')",
            name="jobs_salary_source_valid",
        ),
        sa.CheckConstraint(
            "status in ('ingesting','ready','failed')", name="jobs_status_valid"
        ),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_is_seed", "jobs", ["is_seed"])
    op.create_index("ix_jobs_seniority", "jobs", ["seniority"])
    op.create_index("ix_jobs_work_mode", "jobs", ["work_mode"])
    op.create_index("ix_jobs_created_at", "jobs", [sa.text("created_at DESC")])
    op.create_index("ix_jobs_structured", "jobs", ["structured"], postgresql_using="gin")
    op.create_index("ix_jobs_required_skills", "jobs", ["required_skills"],
                    postgresql_using="gin", postgresql_ops={"required_skills": "jsonb_path_ops"})
    op.create_index("ix_jobs_search_tsv", "jobs", ["search_tsv"], postgresql_using="gin")
    op.create_index("ix_jobs_title_trgm", "jobs", ["title"],
                    postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"})
    op.create_index("ix_jobs_company_trgm", "jobs", ["company"],
                    postgresql_using="gin", postgresql_ops={"company": "gin_trgm_ops"})
    op.create_index("uq_jobs_seed_source_ref", "jobs", ["source_ref"], unique=True,
                    postgresql_where=sa.text("is_seed"))
    op.execute("CREATE TRIGGER trg_jobs_set_updated_at BEFORE UPDATE ON jobs "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "job_chunks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True)),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("section", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("embed_model", sa.String(60), nullable=False),
        sa.Column("embed_dim", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("chunk_tsv", pg.TSVECTOR,
                  sa.Computed("to_tsvector('english'::regconfig, content)", persisted=True)),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.UniqueConstraint("job_id", "chunk_index", name="uq_job_chunks_job_chunk"),
        sa.CheckConstraint("section in ('description','responsibilities','requirements')",
                           name="job_chunks_section_valid"),
    )
    op.create_index("ix_job_chunks_job_id", "job_chunks", ["job_id"])
    op.create_index("ix_job_chunks_chunk_tsv", "job_chunks", ["chunk_tsv"], postgresql_using="gin")
    op.create_index("ix_job_chunks_embedding", "job_chunks", ["embedding"],
                    postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64},
                    postgresql_ops={"embedding": "vector_cosine_ops"})
    op.execute("CREATE TRIGGER trg_job_chunks_set_updated_at BEFORE UPDATE ON job_chunks "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_job_chunks_set_updated_at ON job_chunks")
    op.drop_table("job_chunks")
    op.execute("DROP TRIGGER IF EXISTS trg_jobs_set_updated_at ON jobs")
    op.drop_table("jobs")
