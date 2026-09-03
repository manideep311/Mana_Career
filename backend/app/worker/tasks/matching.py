"""``score_match`` -- the ARQ worker task behind ``MatchService.get_or_create``.

Runs the pure :func:`app.domain.matching.scorer.score` over two freshly built
snapshots, derives deterministic skill-gap drafts, then makes two **non-fatal**
LLM prose calls (a narrative + per-gap rationales -- both return ``None`` / ``{}``
on failure and never raise), and persists the lot through
:meth:`MatchService.apply_score`. The worker owns the single ``session.commit()``.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.llm.factory import get_llm_provider
from app.domain.matching.explainer import GapRationaleWriter, MatchExplainer
from app.domain.matching.gaps import derive_gaps
from app.domain.matching.scorer import inputs_hash, score
from app.domain.matching.service import MatchService
from app.domain.rag.service import RagService
from app.domain.rag.types import RetrievalSource
from app.models.job import Job
from app.models.match import JobMatch
from app.worker.dead_letter import record_failure
from app.worker.tasks.resume import MAX_TRIES

__all__ = ["score_match"]

log = get_logger("worker.score_match")


@contextlib.asynccontextmanager
async def _session_for() -> AsyncIterator[AsyncSession]:
    """Session seam for the résumé pipeline.

    Production opens a fresh ``AsyncSessionLocal`` (its own transaction, closed
    on exit). The DB-backed test monkeypatches this to an async-CM that yields
    the shared rolled-back ``db_session`` without closing it, so every
    ``session.commit()`` below just releases/re-opens that session's SAVEPOINT
    (``join_transaction_mode="create_savepoint"``) and the fixture's outer
    ``trans.rollback()`` still discards the whole test's writes.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def score_match(ctx: dict[str, Any], job_match_id: str) -> dict[str, Any]:
    settings = get_settings()

    async with _session_for() as session:
        m = await session.get(JobMatch, uuid.UUID(job_match_id))
        if m is None:
            await record_failure(
                "score_match",
                args=(job_match_id,),
                kwargs={},
                error=RuntimeError(f"match {job_match_id} not found"),
            )
            return {"job_match_id": job_match_id, "status": "missing"}

        try:
            svc = MatchService(session, settings=settings)
            profile = await svc.build_profile_snapshot(m.user_id)

            # Semantic dimension: curate the job chunks the scorer averages via
            # RAG retrieval over the profile summary. Read-only -- no writes, no
            # commit, no enqueue. Its own try/except degrades a rag/embedding
            # failure to ``None`` (the pre-Phase-6 all-chunks path) rather than
            # letting it bubble into the F3 retry block below.
            rag_sub: list[tuple[float, ...]] | None = None
            if profile.summary_text:
                try:
                    rag = RagService(session, get_embeddings_provider(settings))
                    retrieved = await rag.retrieve(
                        profile.summary_text,
                        source=RetrievalSource.JOB_CHUNKS,
                        user_id=m.user_id,
                        job_id=m.job_id,
                        k=8,
                    )
                    rag_sub = [
                        b.embedding for b in retrieved.blocks if b.embedding is not None
                    ] or None
                except Exception:
                    log.warning(
                        "score_match_rag_retrieve_failed",
                        job_match_id=job_match_id,
                        exc_info=True,
                    )
                    rag_sub = None
            job = await svc.build_job_snapshot(m.job_id, chunk_embeddings=rag_sub)
            expected_hash = inputs_hash(profile, job)
            if m.status == "ready" and m.inputs_hash == expected_hash:
                return {"job_match_id": job_match_id, "status": "skipped"}

            emb = (
                await get_embeddings_provider(settings).embed_query(profile.summary_text)
                if profile.summary_text
                else None
            )
            result = score(profile, job, profile_embedding=tuple(emb) if emb else None)

            skill_comp = next(c for c in result.components if c.dimension == "skill")
            # build_job_snapshot() above already 404s a missing Job; the guard is
            # for the type-checker (session.get -> Job | None).
            job_row = await session.get(Job, m.job_id)
            if job_row is None:  # pragma: no cover
                raise RuntimeError(f"job {m.job_id} not found")
            drafts = derive_gaps(
                job_row.required_skills, job_row.preferred_skills, skill_comp
            )

            explainer = MatchExplainer(
                get_llm_provider(settings), model=settings.llm_model_extraction
            )
            narrative = await explainer.explain(
                job_title=job_row.title or "",
                company=job_row.company,
                result=result,
            )
            expl_meta = {
                "model": explainer.last_usage.model if explainer.last_usage else "unknown"
            }
            rationales = await GapRationaleWriter(
                get_llm_provider(settings), model=settings.llm_model_extraction
            ).write(job_title=job_row.title or "", gaps=drafts)

            await svc.apply_score(
                m.id,
                result=result,
                gaps=drafts,
                explanation=narrative,
                explanation_meta=expl_meta,
                rationales=rationales,
            )
            await session.commit()
            log.info(
                "match_scored",
                job_match_id=job_match_id,
                score=result.score,
                band=result.band,
                gaps=len(drafts),
            )
            return {
                "job_match_id": job_match_id,
                "status": "ready",
                "score": result.score,
            }
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise  # transient — let ARQ retry, don't surface a terminal failure
            m = await session.get(JobMatch, uuid.UUID(job_match_id))
            if m is not None:
                await MatchService(session).mark_failed(
                    m.id, "We couldn't score this job."
                )
                await session.commit()
            await record_failure(
                "score_match", args=(job_match_id,), kwargs={}, error=exc
            )
            raise
