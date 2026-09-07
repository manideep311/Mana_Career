"""learning_resources + learning_recommendations + roadmap_milestones

Revision ID: 0015_learning_roadmap
Revises: 0014_application_events
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0015_learning_roadmap"
down_revision = "0014_application_events"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def _updated_at_trigger(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def upgrade() -> None:
    op.create_table(
        "learning_resources",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("url", sa.String(500), nullable=False, unique=True),
        sa.Column("type", sa.String(12), nullable=False),
        sa.Column("skills", sa.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("est_hours", sa.Integer),
        sa.Column("cost", sa.String(10), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("type in ('course','book','doc','video','article','project')",
                           name="learning_resources_type_valid"),
        sa.CheckConstraint("level in ('beginner','intermediate','advanced')",
                           name="learning_resources_level_valid"),
        sa.CheckConstraint("cost in ('free','paid','freemium')",
                           name="learning_resources_cost_valid"),
    )
    op.create_index("ix_learning_resources_embedding", "learning_resources", ["embedding"],
                    postgresql_using="hnsw",
                    postgresql_ops={"embedding": "vector_cosine_ops"})
    op.create_index("ix_learning_resources_skills", "learning_resources", ["skills"],
                    postgresql_using="gin")
    op.create_index("ix_learning_resources_level", "learning_resources", ["level"])
    _updated_at_trigger("learning_resources")

    op.create_table(
        "learning_recommendations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("constraints", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", sa.Text),
        sa.Column("next_step", sa.Text),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'planning'")),
        sa.Column("generation_meta", pg.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("scope in ('aggregate','job')",
                           name="learning_recommendations_scope_valid"),
        sa.CheckConstraint("status in ('planning','active','archived')",
                           name="learning_recommendations_status_valid"),
    )
    op.create_index("ix_learning_recommendations_user", "learning_recommendations",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_learning_recommendations_user_status", "learning_recommendations",
                    ["user_id", "status"])
    _updated_at_trigger("learning_recommendations")

    op.create_table(
        "roadmap_milestones",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("recommendation_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("learning_recommendations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("skill_id", pg.UUID(as_uuid=True)),
        sa.Column("skill_slug", sa.String(120), nullable=False),
        sa.Column("skill_label", sa.String(160), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("why_it_matters", sa.Text, nullable=False),
        sa.Column("resource_ids", sa.ARRAY(pg.UUID(as_uuid=True)), nullable=False,
                  server_default=sa.text("'{}'")),
        sa.Column("est_hours", sa.Integer),
        sa.Column("practice_project", sa.Text),
        sa.Column("checkpoint", sa.Text),
        sa.Column("status", sa.String(12), nullable=False,
                  server_default=sa.text("'not_started'")),
        sa.Column("completed_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("status in ('not_started','in_progress','done')",
                           name="roadmap_milestones_status_valid"),
    )
    op.create_index("ix_roadmap_milestones_rec", "roadmap_milestones",
                    ["recommendation_id", "order_index"])
    op.create_index("ix_roadmap_milestones_user", "roadmap_milestones", ["user_id"])
    _updated_at_trigger("roadmap_milestones")


def downgrade() -> None:
    for t in ("roadmap_milestones", "learning_recommendations", "learning_resources"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_set_updated_at ON {t}")
        op.drop_table(t)
