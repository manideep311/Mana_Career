from __future__ import annotations

from app.core.config import Settings
from app.domain.embeddings.adapters.fake import FakeEmbeddingsProvider
from app.domain.embeddings.provider import EmbeddingsProvider


def get_embeddings_provider(settings: Settings) -> EmbeddingsProvider:
    if settings.embeddings_provider == "fake":
        return FakeEmbeddingsProvider(settings.embed_dim, settings.embed_model)
    raise NotImplementedError(
        f"{settings.embeddings_provider!r} embeddings adapter lands in Phase 6"
    )
