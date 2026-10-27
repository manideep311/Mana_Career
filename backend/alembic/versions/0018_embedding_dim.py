"""embedding columns take their size from EMBED_DIM (384 for the local model)

Every vector column was created as vector(1024) (Voyage's size). This resizes
each one to EMBED_DIM and rebuilds its HNSW index. Vectors of the old size
can't be converted, so they are cleared: run ``python -m app.reembed`` (or
``just reembed``) afterwards on a database that already has data. A fresh
database is unaffected; the seed fills it at the new size.

With EMBED_DIM=1024 (Voyage) this changes nothing.

Revision ID: 0018_embedding_dim
Revises: 0017_auth_tokens
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

from app.models.vector import EMBED_DIM

revision = "0018_embedding_dim"
down_revision = "0017_auth_tokens"
branch_labels = None
depends_on = None

_OLD_DIM = 1024
# (table, HNSW index, index build options) for every vector column.
_VECTOR_COLUMNS: tuple[tuple[str, str, dict[str, int]], ...] = (
    ("skills", "ix_skills_embedding", {"m": 16, "ef_construction": 64}),
    ("job_chunks", "ix_job_chunks_embedding", {"m": 16, "ef_construction": 64}),
    ("resume_chunks", "ix_resume_chunks_embedding", {"m": 16, "ef_construction": 64}),
    ("learning_resources", "ix_learning_resources_embedding", {}),
)


def _resize(dim: int) -> None:
    conn = op.get_bind()
    for table, index, options in _VECTOR_COLUMNS:
        current = conn.execute(
            sa.text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = CAST(:t AS regclass) AND attname = 'embedding'"
            ),
            {"t": table},
        ).scalar_one()
        if current == f"vector({dim})":
            continue
        op.drop_index(index, table_name=table)
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector({dim}) "
            f"USING NULL::vector({dim})"
        )
        op.create_index(
            index, table, ["embedding"],
            postgresql_using="hnsw",
            postgresql_with=options,
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )
    op.execute(f"ALTER TABLE resume_chunks ALTER COLUMN embed_dim SET DEFAULT {dim}")


def upgrade() -> None:
    _resize(EMBED_DIM)


def downgrade() -> None:
    _resize(_OLD_DIM)
