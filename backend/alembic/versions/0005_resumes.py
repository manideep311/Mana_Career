"""resumes table (upload → extraction lifecycle)

Revision ID: 0005_resumes
Revises: 0004_career_profiles
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0005_resumes"
down_revision = "0004_career_profiles"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "resumes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("original_filename", sa.String(300)),
        sa.Column("file_ref", sa.String(400), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("page_count", sa.Integer),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'uploaded'")),
        sa.Column("parse_error", sa.Text),
        sa.Column("extracted_text", sa.Text),
        sa.Column("extraction", pg.JSONB),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("confirmed_at", _TS),
        sa.Column("deleted_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "status in ('uploaded','parsing','parsed','extracting','extracted','failed')",
            name="resumes_status_valid",
        ),
    )
    op.create_index("uq_resumes_user_primary", "resumes", ["user_id"], unique=True,
                    postgresql_where=sa.text("is_primary AND deleted_at IS NULL"))
    op.create_index("ix_resumes_user_created", "resumes", ["user_id", sa.text("created_at DESC")])
    op.execute(
        "CREATE TRIGGER trg_resumes_set_updated_at BEFORE UPDATE ON resumes "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_resumes_set_updated_at ON resumes")
    op.drop_table("resumes")
