"""applications + approval_requests tables

Revision ID: 0013_applications_approvals
Revises: 0012_application_documents
Create Date: 2026-09-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0013_applications_approvals"
down_revision = "0012_application_documents"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("resume_version_id", pg.UUID(as_uuid=True)),
        sa.Column("cover_letter_id", pg.UUID(as_uuid=True)),
        sa.Column("application_email_id", pg.UUID(as_uuid=True)),
        # String(20): 'awaiting_approval' is 17 chars (also why ai_sessions.status
        # is String(20)). approval_requests.status below stays String(16) -- its
        # longest value 'superseded' is 10.
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'preparing'")),
        sa.Column("match_score", sa.Numeric(5, 2)),
        sa.Column("source", sa.String(16), nullable=False,
                  server_default=sa.text("'mana_ai'")),
        sa.Column("ai_session_id", pg.UUID(as_uuid=True)),
        sa.Column("applied_at", _TS),
        sa.Column("last_status_change_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("notes", sa.Text),
        sa.Column("deleted_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "status in ('saved','preparing','awaiting_approval','applied',"
            "'interview','offer','rejected','withdrawn')",
            name="applications_status_valid",
        ),
        sa.CheckConstraint(
            "source in ('user','mana_ai')", name="applications_source_valid"
        ),
    )
    op.create_index("ix_applications_user_status", "applications", ["user_id", "status"])
    op.create_index("ix_applications_user_updated", "applications",
                    ["user_id", sa.text("updated_at DESC")])
    op.create_index("ix_applications_job", "applications", ["job_id"])
    op.execute("CREATE TRIGGER trg_applications_set_updated_at BEFORE UPDATE ON "
               "applications FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "approval_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False,
                  server_default=sa.text("'send_application_email'")),
        sa.Column("payload_snapshot", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("decided_by", pg.UUID(as_uuid=True)),
        sa.Column("decided_at", _TS),
        sa.Column("decision_note", sa.Text),
        sa.Column("expires_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "action_type in ('send_application_email')",
            name="approval_requests_action_type_valid",
        ),
        sa.CheckConstraint(
            "status in ('pending','approved','rejected','superseded','expired')",
            name="approval_requests_status_valid",
        ),
    )
    op.create_index("ix_approval_requests_user_status", "approval_requests",
                    ["user_id", "status"])
    op.create_index("uq_approval_requests_run_pending", "approval_requests",
                    ["run_id", "action_type"], unique=True,
                    postgresql_where=sa.text("status = 'pending'"))
    op.execute("CREATE TRIGGER trg_approval_requests_set_updated_at BEFORE UPDATE ON "
               "approval_requests FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    # application_emails.status (migration 0012) was String(16), but its CHECK
    # allows 'awaiting_approval' (17 chars) -- Phase 10a's email_external_action
    # is the first code path that ever writes a value that long. Widen it here
    # rather than in a separate 0014.
    op.alter_column("application_emails", "status", type_=sa.String(20))


def downgrade() -> None:
    op.alter_column("application_emails", "status", type_=sa.String(16))
    op.execute("DROP TRIGGER IF EXISTS trg_approval_requests_set_updated_at "
               "ON approval_requests")
    op.drop_table("approval_requests")
    op.execute("DROP TRIGGER IF EXISTS trg_applications_set_updated_at ON applications")
    op.drop_table("applications")
