from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.domain.embeddings.provider import EmbeddingsProvider
from app.domain.rag.context import DEFAULT_TOKEN_BUDGET, assemble_context
from app.domain.rag.fusion import mmr, rrf
from app.domain.rag.reranker import NoopReranker, Reranker
from app.domain.rag.types import RetrievalSource, RetrievedContext, ScoredChunk
from app.domain.rag.vector_store import VectorStore


def _empty(query: str) -> RetrievedContext:
    return RetrievedContext(blocks=(), text="", citations=(), total_tokens=0, query=query)


class RagService:
    def __init__(
        self,
        session: AsyncSession,
        embeddings: EmbeddingsProvider,
        *,
        reranker: Reranker | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._store = VectorStore(session)
        self._embeddings = embeddings
        self._reranker: Reranker = reranker or NoopReranker()
        self._settings = settings or get_settings()

    async def retrieve(
        self,
        query: str,
        *,
        source: RetrievalSource,
        user_id: uuid.UUID,
        job_id: uuid.UUID | None = None,
        k: int = 8,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> RetrievedContext:
        if not query.strip():
            return _empty(query)

        qemb = await self._embeddings.embed_query(query)
        vec = await self._store.vector_search(
            source=source, query_embedding=qemb, user_id=user_id, job_id=job_id
        )
        txt = await self._store.text_search(
            source=source, query_text=query, user_id=user_id, job_id=job_id
        )
        if not vec and not txt:
            return _empty(query)

        fused = rrf([c.ref_id for c in vec], [c.ref_id for c in txt])
        by_id: dict[str, ScoredChunk] = {}
        for c in (*txt, *vec):  # vec last so its embedding/content win
            prev = by_id.get(c.ref_id)
            embedding = c.embedding
            if embedding is None and prev is not None:
                embedding = prev.embedding
            vector_rank = c.vector_rank
            if vector_rank is None and prev is not None:
                vector_rank = prev.vector_rank
            text_rank = c.text_rank
            if text_rank is None and prev is not None:
                text_rank = prev.text_rank
            by_id[c.ref_id] = ScoredChunk(
                ref_id=c.ref_id,
                source=c.source,
                section=c.section,
                content=c.content,
                token_count=c.token_count,
                embedding=embedding,
                vector_rank=vector_rank,
                text_rank=text_rank,
                rrf_score=fused.get(c.ref_id, 0.0),
                mmr_score=None,
            )
        candidates = sorted(by_id.values(), key=lambda c: (-c.rrf_score, c.ref_id))
        candidates = await self._reranker.rerank(query, candidates)
        selected = mmr(candidates, k=k)
        return assemble_context(selected, token_budget=token_budget, query=query)
