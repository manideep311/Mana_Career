"""Embeddings computed on this machine's CPU with fastembed (ONNX Runtime).

BAAI/bge-small-en-v1.5 makes 384-dimension vectors from up to 512 tokens. Its
model card asks for an instruction in front of short retrieval *queries* and
nothing in front of the stored passages; fastembed leaves that to the caller,
so :meth:`embed_query` adds it here.

The model (about 67 MB, int8-quantised by Qdrant) is loaded once per process,
on first use, and shared. The Docker image downloads it at build time
(``FASTEMBED_CACHE_PATH``), so a cold start reads it from disk.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from app.core.config import LOCAL_EMBED_MODELS

if TYPE_CHECKING:
    from fastembed import TextEmbedding

BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_models: dict[tuple[str, str | None], TextEmbedding] = {}
_lock = threading.Lock()


def load_model(model: str, cache_dir: str | None = None) -> TextEmbedding:
    """The shared fastembed model, loading it on first use."""
    key = (model, cache_dir)
    with _lock:
        if key not in _models:
            # Imported lazily: onnxruntime is heavy, and only this provider needs it.
            from fastembed import TextEmbedding

            _models[key] = TextEmbedding(model_name=model, cache_dir=cache_dir)
        return _models[key]


class LocalEmbeddingsProvider:
    _BATCH = 32

    def __init__(self, *, model: str, dim: int, cache_dir: str | None = None) -> None:
        if LOCAL_EMBED_MODELS.get(model) != dim:
            raise ValueError(f"local embeddings: {model} does not make {dim}-d vectors")
        self._model = model
        self._dim = dim
        self._cache_dir = cache_dir

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return self._model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._embed, texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await asyncio.to_thread(self._embed, [BGE_QUERY_INSTRUCTION + text]))[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = load_model(self._model, self._cache_dir)
        vectors = [v.tolist() for v in model.embed(texts, batch_size=self._BATCH)]
        if any(len(v) != self._dim for v in vectors):
            raise RuntimeError("local embeddings returned a vector of the wrong dimension")
        return vectors
