from __future__ import annotations

from typing import Protocol

from app.domain.rag.types import ScoredChunk


class Reranker(Protocol):
    async def rerank(self, query: str, chunks: list[ScoredChunk]) -> list[ScoredChunk]: ...


class NoopReranker:
    async def rerank(self, query: str, chunks: list[ScoredChunk]) -> list[ScoredChunk]:
        return chunks
