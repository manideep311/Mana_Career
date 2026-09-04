"""resume_versions + resume_chunks + resume_suggestions tables

Revision ID: 0011_resume_tailoring
Revises: 0010_ai
Create Date: 2026-09-04
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0011_resume_tailoring"
down_revision = "0010_ai"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "resume_versions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True)),
        sa.Column("application_id", pg.UUID(as_uuid=True)),
        sa.Column("parent_version_id", pg.UUID(as_uuid=True)),
        sa.Column("label", sa.String(120)),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("rendered_refs", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("generation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.String(16), nullable=False,
                  server_default=sa.text("'user'")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "kind in ('base_snapshot','manual_edit','ai_tailored')",
            name="resume_versions_kind_valid",
        ),
        sa.CheckConstraint(
            "created_by in ('user','mana_ai')",
            name="resume_versions_created_by_valid",
        ),
    )
    op.create_index("ix_resume_versions_resume", "resume_versions",
                    ["resume_id", sa.text("created_at DESC")])
    op.create_index("ix_resume_versions_user", "resume_versions", ["user_id"])
    op.create_index("ix_resume_versions_job", "resume_versions", ["job_id"])
    op.execute("CREATE TRIGGER trg_resume_versions_set_updated_at BEFORE UPDATE ON "
               "resume_versions FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "resume_chunks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("resume_version_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("section", sa.String(40), nullable=False),
        sa.Column("ref_id", sa.String(80)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("embed_model", sa.String(80), nullable=False,
                  server_default=sa.text("'fake-embed-1'")),
        sa.Column("embed_dim", sa.Integer, nullable=False, server_default=sa.text("1024")),
        sa.Column("embedding", Vector(1024)),
        sa.Column("content_tsv", pg.TSVECTOR,
                  sa.Computed("to_tsvector('english', content)", persisted=True)),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
    )
    op.create_index("ix_resume_chunks_version", "resume_chunks",
                    ["resume_version_id", "chunk_index"])
    op.create_index("ix_resume_chunks_content_tsv", "resume_chunks", ["content_tsv"],
                    postgresql_using="gin")
    op.create_index("ix_resume_chunks_embedding", "resume_chunks", ["embedding"],
                    postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64},
                    postgresql_ops={"embedding": "vector_cosine_ops"})
    op.execute("CREATE TRIGGER trg_resume_chunks_set_updated_at BEFORE UPDATE ON "
               "resume_chunks FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "resume_suggestions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_version_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(40), nullable=False),
        sa.Column("target_ref_id", sa.String(80)),
        sa.Column("suggestion_type", sa.String(24), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("proposed_change", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'open'")),
        sa.Column("resulting_version_id", pg.UUID(as_uuid=True)),
        sa.Column("source", sa.String(16), nullable=False,
                  server_default=sa.text("'mana_ai'")),
        sa.Column("generation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "status in ('open','accepted','edited','dismissed')",
            name="resume_suggestions_status_valid",
        ),
    )
    op.create_index("ix_resume_suggestions_user", "resume_suggestions",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_resume_suggestions_version", "resume_suggestions",
                    ["resume_version_id"])
    op.execute("CREATE TRIGGER trg_resume_suggestions_set_updated_at BEFORE UPDATE ON "
               "resume_suggestions FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_resume_suggestions_set_updated_at "
               "ON resume_suggestions")
    op.drop_table("resume_suggestions")
    op.execute("DROP TRIGGER IF EXISTS trg_resume_chunks_set_updated_at ON resume_chunks")
    op.drop_table("resume_chunks")
    op.execute("DROP TRIGGER IF EXISTS trg_resume_versions_set_updated_at ON resume_versions")
    op.drop_table("resume_versions")
