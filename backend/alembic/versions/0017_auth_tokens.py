"""auth_tokens: single-use emailed links (password reset, email verification)

Revision ID: 0017_auth_tokens
Revises: 0016_email_delivered_to
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0017_auth_tokens"
down_revision = "0016_email_delivered_to"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "auth_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("used_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "purpose in ('password_reset','email_verify')", name="auth_token_purpose_valid"
        ),
    )
    op.create_index("uq_auth_tokens_token_hash", "auth_tokens", ["token_hash"], unique=True)
    op.create_index(
        "ix_auth_tokens_user_purpose_created", "auth_tokens",
        ["user_id", "purpose", "created_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_auth_tokens_set_updated_at BEFORE UPDATE ON auth_tokens "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_auth_tokens_set_updated_at ON auth_tokens")
    op.drop_index("ix_auth_tokens_user_purpose_created", table_name="auth_tokens")
    op.drop_index("uq_auth_tokens_token_hash", table_name="auth_tokens")
    op.drop_table("auth_tokens")
