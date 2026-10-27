"""The one vector size every embedding column uses.

Read from ``EMBED_DIM`` (environment or ``.env``), the same variable
``Settings.embed_dim`` reads, so the models, the migrations and the providers
can't disagree. 384 suits the default local model (bge-small-en-v1.5); Voyage
needs 1024. Changing it on an existing database: ``python -m app.reembed``.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class _VectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # pgvector's HNSW index takes at most 2000 dimensions.
    embed_dim: int = Field(default=384, ge=1, le=2000)


EMBED_DIM: int = _VectorSettings().embed_dim
