"""eval_runs + eval_results tables

Revision ID: 0009_eval
Revises: 0008_matches
Create Date: 2026-09-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0009_eval"
down_revision = "0008_matches"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("suite", sa.String(16), nullable=False),
        sa.Column("dataset_ref", sa.String(200), nullable=False),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("git_sha", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_ids", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("config", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'running'")),
        sa.Column("started_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("ended_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("suite in ('retrieval','generation','matching')",
                           name="eval_runs_suite_valid"),
        sa.CheckConstraint("status in ('running','passed','failed','error')",
                           name="eval_runs_status_valid"),
    )
    op.execute("CREATE TRIGGER trg_eval_runs_set_updated_at BEFORE UPDATE ON eval_runs "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "eval_results",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("eval_run_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(80), nullable=False),
        sa.Column("input", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("expected", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("scores", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("judge_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
    )
    op.create_index("ix_eval_results_run", "eval_results", ["eval_run_id"])
    op.execute("CREATE TRIGGER trg_eval_results_set_updated_at BEFORE UPDATE ON eval_results "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_eval_results_set_updated_at ON eval_results")
    op.drop_table("eval_results")
    op.execute("DROP TRIGGER IF EXISTS trg_eval_runs_set_updated_at ON eval_runs")
    op.drop_table("eval_runs")
