"""application_emails.delivered_to: where an application email actually went

In the default "redirect" delivery mode the email reaches the applicant's own
inbox rather than the employer, so the intended recipient (to_email) and the
real one can differ; both are kept.

Revision ID: 0016_email_delivered_to
Revises: 0015_learning_roadmap
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_email_delivered_to"
down_revision = "0015_learning_roadmap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_emails", sa.Column("delivered_to", sa.String(320), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("application_emails", "delivered_to")
