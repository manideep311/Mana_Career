"""audit_logs (append-only)

Revision ID: 0002_audit_logs
Revises: 0001_bootstrap
Create Date: 2026-08-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0002_audit_logs"
down_revision = "0001_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True)),
        sa.Column("on_behalf_of_user_id", pg.UUID(as_uuid=True)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", pg.UUID(as_uuid=True)),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("before", pg.JSONB),
        sa.Column("after", pg.JSONB),
        sa.Column(
            "result", sa.String(16), nullable=False, server_default=sa.text("'success'")
        ),
        sa.Column("meta", pg.JSONB),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "actor_type in ('user','mana_ai','system')", name="actor_type_valid"
        ),
        sa.CheckConstraint("result in ('success','failure')", name="result_valid"),
    )
    op.create_index(
        "ix_audit_actor_created", "audit_logs", ["actor_user_id", "created_at"]
    )
    op.create_index("ix_audit_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_action_created", "audit_logs", ["action", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
