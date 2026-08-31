from __future__ import annotations

import hashlib
import math
import random


class FakeEmbeddingsProvider:
    """Deterministic offline embeddings: same text -> same unit vector."""

    def __init__(self, dim: int, model: str) -> None:
        self._dim = dim
        self._model = model

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return self._model

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        rng = random.Random(digest)  # noqa: S311  test/dev fixture, not security-sensitive
        raw = [rng.uniform(-1.0, 1.0) for _ in range(self._dim)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
