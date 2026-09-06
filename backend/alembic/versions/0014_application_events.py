"""application_events (append-only)

Revision ID: 0014_application_events
Revises: 0013_applications_approvals
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0014_application_events"
down_revision = "0013_applications_approvals"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "application_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("application_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20)),
        sa.Column("body", sa.Text),
        sa.Column("meta", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "kind in ('status_change','note','interview_scheduled','ai_action','email_sent')",
            name="application_events_kind_valid",
        ),
    )
    op.create_index("ix_application_events_app", "application_events",
                    ["application_id", sa.text("occurred_at DESC")])
    op.create_index("ix_application_events_user", "application_events", ["user_id"])


def downgrade() -> None:
    op.drop_table("application_events")
