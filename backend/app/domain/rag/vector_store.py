from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rag.types import RetrievalSource, ScoredChunk
from app.models.job import JobChunk

VECTOR_TOP_N = 30
TEXT_TOP_N = 30


def _row_to_chunk(
    row: JobChunk, source: RetrievalSource, *, vector_rank: int | None, text_rank: int | None
) -> ScoredChunk:
    return ScoredChunk(
        ref_id=f"{row.job_id}:{row.chunk_index}",
        source=source,
        section=row.section,
        content=row.content,
        token_count=row.token_count,
        embedding=(
            tuple(float(x) for x in row.embedding) if row.embedding is not None else None
        ),
        vector_rank=vector_rank,
        text_rank=text_rank,
        rrf_score=0.0,
        mmr_score=None,
    )


class VectorStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _guard(self, source: RetrievalSource) -> None:
        if source is not RetrievalSource.JOB_CHUNKS:
            raise NotImplementedError(f"{source} retrieval lands in a later phase")

    async def vector_search(
        self, *, source: RetrievalSource, query_embedding: list[float],
        user_id: uuid.UUID, job_id: uuid.UUID | None = None, k: int = VECTOR_TOP_N,
    ) -> list[ScoredChunk]:
        self._guard(source)
        stmt = (
            select(JobChunk)
            .where(
                JobChunk.embedding.isnot(None),
                or_(JobChunk.owner_id.is_(None), JobChunk.owner_id == user_id),
            )
            .order_by(JobChunk.embedding.cosine_distance(query_embedding))
            .limit(k)
        )
        if job_id is not None:
            stmt = stmt.where(JobChunk.job_id == job_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            _row_to_chunk(r, source, vector_rank=i, text_rank=None)
            for i, r in enumerate(rows, start=1)
        ]

    async def text_search(
        self, *, source: RetrievalSource, query_text: str,
        user_id: uuid.UUID, job_id: uuid.UUID | None = None, k: int = TEXT_TOP_N,
    ) -> list[ScoredChunk]:
        self._guard(source)
        tsq = func.websearch_to_tsquery("english", query_text)
        stmt = (
            select(JobChunk)
            .where(
                JobChunk.chunk_tsv.op("@@")(tsq),
                or_(JobChunk.owner_id.is_(None), JobChunk.owner_id == user_id),
            )
            .order_by(func.ts_rank_cd(JobChunk.chunk_tsv, tsq).desc())
            .limit(k)
        )
        if job_id is not None:
            stmt = stmt.where(JobChunk.job_id == job_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            _row_to_chunk(r, source, vector_rank=None, text_rank=i)
            for i, r in enumerate(rows, start=1)
        ]
