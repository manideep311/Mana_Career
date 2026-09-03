from __future__ import annotations

from app.core.config import Settings
from app.domain.embeddings.adapters.fake import FakeEmbeddingsProvider
from app.domain.embeddings.adapters.voyage import VoyageEmbeddingsProvider
from app.domain.embeddings.provider import EmbeddingsProvider


def get_embeddings_provider(settings: Settings) -> EmbeddingsProvider:
    if settings.embeddings_provider == "fake":
        return FakeEmbeddingsProvider(settings.embed_dim, settings.embed_model)
    if settings.embeddings_provider == "voyage":
        key = settings.voyage_api_key.get_secret_value() if settings.voyage_api_key else ""
        if not key:
            raise RuntimeError("VOYAGE_API_KEY is required for the voyage embeddings provider")
        return VoyageEmbeddingsProvider(
            api_key=key, model=settings.embed_model, dim=settings.embed_dim
        )
    raise NotImplementedError(
        f"{settings.embeddings_provider!r} embeddings adapter lands in Phase 6"
    )
