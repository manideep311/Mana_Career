"""bootstrap extensions and shared trigger

Revision ID: 0001_bootstrap
Revises:
Create Date: 2026-08-30
"""
from alembic import op

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for ext in ("vector", "pg_trgm", "citext", "pgcrypto"):
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    for ext in ("vector", "pg_trgm", "citext", "pgcrypto"):
        op.execute(f'DROP EXTENSION IF EXISTS "{ext}"')
