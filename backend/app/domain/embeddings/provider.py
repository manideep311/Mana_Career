from __future__ import annotations

from typing import Protocol


class EmbeddingsProvider(Protocol):
    @property
    def dim(self) -> int: ...

    @property
    def model(self) -> str: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...
