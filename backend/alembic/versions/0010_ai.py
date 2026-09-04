"""ai_sessions + messages + ai_actions + agent_steps tables

Revision ID: 0010_ai
Revises: 0009_eval
Create Date: 2026-09-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0010_ai"
down_revision = "0009_eval"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "ai_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("goal", sa.String(32)),
        sa.Column("title", sa.String(200)),
        sa.Column("context", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'idle'")),
        sa.Column("run_id", sa.String(64)),
        sa.Column("run_config", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("budget", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("totals", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text),
        sa.Column("started_at", _TS),
        sa.Column("ended_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("kind in ('chat','agent_run')",
                           name="ai_sessions_kind_valid"),
        sa.CheckConstraint(
            "status in ('idle','running','awaiting_approval','completed',"
            "'rejected','halted','error')",
            name="ai_sessions_status_valid"),
    )
    op.create_index("ix_ai_sessions_user", "ai_sessions",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_ai_sessions_status", "ai_sessions", ["status"])
    op.create_index("ix_ai_sessions_run", "ai_sessions", ["run_id"])
    op.execute("CREATE TRIGGER trg_ai_sessions_set_updated_at BEFORE UPDATE ON ai_sessions "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.create_table(
        "messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("ai_session_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("blocks", pg.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("tool_calls", pg.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("tool_call_id", sa.String(64)),
        sa.Column("citations", pg.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("token_usage", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("model_id", sa.String(80)),
        sa.Column("provider", sa.String(32)),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("role in ('user','assistant','tool','system')",
                           name="messages_role_valid"),
    )
    op.create_index("ix_messages_session", "messages", ["ai_session_id", "created_at"])

    op.create_table(
        "ai_actions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_session_id", pg.UUID(as_uuid=True)),
        sa.Column("run_id", sa.String(64)),
        sa.Column("node", sa.String(40), nullable=False),
        sa.Column("action_key", sa.String(60), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("detail", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("entity_type", sa.String(40)),
        sa.Column("entity_id", pg.UUID(as_uuid=True)),
        sa.Column("status", sa.String(12), nullable=False,
                  server_default=sa.text("'ok'")),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(8, 4)),
        sa.Column("occurred_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("status in ('ok','warning','error')",
                           name="ai_actions_status_valid"),
    )
    op.create_index("ix_ai_actions_user", "ai_actions",
                    ["user_id", sa.text("occurred_at DESC")])

    op.create_table(
        "agent_steps",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("ai_session_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("node", sa.String(40), nullable=False),
        sa.Column("input_summary", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_summary", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("llm_calls", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tool_calls", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("cost_usd", sa.Numeric(8, 4), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("started_at", _TS),
        sa.Column("ended_at", _TS),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "status in ('ok','deduped','skipped_fresh','error','budget_exceeded')",
            name="agent_steps_status_valid"),
    )
    op.create_index("ix_agent_steps_run", "agent_steps", ["run_id", "step_index"])
    op.execute("CREATE TRIGGER trg_agent_steps_set_updated_at BEFORE UPDATE ON agent_steps "
               "FOR EACH ROW EXECUTE FUNCTION set_updated_at()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_agent_steps_set_updated_at ON agent_steps")
    op.drop_table("agent_steps")
    op.drop_table("ai_actions")
    op.drop_table("messages")
    op.execute("DROP TRIGGER IF EXISTS trg_ai_sessions_set_updated_at ON ai_sessions")
    op.drop_table("ai_sessions")
