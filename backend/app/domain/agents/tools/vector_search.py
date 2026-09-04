from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.embeddings.provider import EmbeddingsProvider
from app.domain.rag.service import RagService
from app.domain.rag.types import RetrievalSource


async def vector_search(
    *,
    session: AsyncSession,
    embeddings: EmbeddingsProvider,
    query: str,
    user_id: uuid.UUID,
    k: int = 10,
) -> list[dict[str, Any]]:
    """Retrieve job-chunk hits for ``query`` via the Phase-6 RAG retriever.

    ``k`` is clamped to ``[1, 20]``. Each hit is ``{"ref_id", "section", "score"}``
    where ``score`` is the chunk's reciprocal-rank-fusion score.
    """
    k = max(1, min(k, 20))
    ctx = await RagService(session, embeddings).retrieve(
        query, source=RetrievalSource.JOB_CHUNKS, user_id=user_id, k=k
    )
    return [{"ref_id": b.ref_id, "section": b.section, "score": b.rrf_score} for b in ctx.blocks]
