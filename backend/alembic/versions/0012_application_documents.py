"""cover_letters + application_emails tables

Revision ID: 0012_application_documents
Revises: 0011_resume_tailoring
Create Date: 2026-09-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0012_application_documents"
down_revision = "0011_resume_tailoring"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "cover_letters",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", pg.UUID(as_uuid=True)),
        sa.Column("resume_version_id", pg.UUID(as_uuid=True)),
        sa.Column("tone", sa.String(24), nullable=False,
                  server_default=sa.text("'professional'")),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_json", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("rendered_refs", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("generation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("supersedes_id", pg.UUID(as_uuid=True)),
        sa.Column("created_by", sa.String(16), nullable=False,
                  server_default=sa.text("'mana_ai'")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "created_by in ('user','mana_ai')",
            name="cover_letters_created_by_valid",
        ),
    )
    op.create_index("ix_cover_letters_user", "cover_letters",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_cover_letters_job", "cover_letters", ["job_id"])
    op.execute("CREATE TRIGGER trg_cover_letters_set_updated_at BEFORE UPDATE ON "
               "cover_letters FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "application_emails",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", pg.UUID(as_uuid=True)),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("to_email", sa.String(320)),
        sa.Column("to_name", sa.String(200)),
        sa.Column("cc", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("bcc", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("body_format", sa.String(8), nullable=False,
                  server_default=sa.text("'plain'")),
        sa.Column("attachment_refs", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'draft'")),
        sa.Column("provider", sa.String(16)),
        sa.Column("provider_message_id", sa.String(200)),
        sa.Column("sent_at", _TS),
        sa.Column("send_error", sa.Text),
        sa.Column("generation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "body_format in ('plain','html')",
            name="application_emails_body_format_valid",
        ),
        sa.CheckConstraint(
            "status in "
            "('draft','awaiting_approval','approved','sending','sent','failed','canceled')",
            name="application_emails_status_valid",
        ),
    )
    op.create_index("ix_application_emails_user", "application_emails",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_application_emails_job", "application_emails", ["job_id"])
    op.execute("CREATE TRIGGER trg_application_emails_set_updated_at BEFORE UPDATE ON "
               "application_emails FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_application_emails_set_updated_at "
               "ON application_emails")
    op.drop_table("application_emails")
    op.execute("DROP TRIGGER IF EXISTS trg_cover_letters_set_updated_at ON cover_letters")
    op.drop_table("cover_letters")
