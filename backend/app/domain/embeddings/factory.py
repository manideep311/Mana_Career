from __future__ import annotations

from app.core.config import Settings
from app.domain.embeddings.adapters.fake import FakeEmbeddingsProvider
from app.domain.embeddings.adapters.voyage import VoyageEmbeddingsProvider
from app.domain.embeddings.provider import EmbeddingsProvider


def get_embeddings_provider(settings: Settings) -> EmbeddingsProvider:
    # Settings validation guarantees the Voyage key is present.
    if settings.embeddings_provider == "voyage" and settings.voyage_api_key is not None:
        return VoyageEmbeddingsProvider(
            api_key=settings.voyage_api_key.get_secret_value(),
            model=settings.embed_model,
            dim=settings.embed_dim,
        )
    return FakeEmbeddingsProvider(settings.embed_dim, settings.embed_model)
