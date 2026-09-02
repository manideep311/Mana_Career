from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.events import job_channel, publish_status
from app.core.logging import get_logger
from app.core.redis import redis_from_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.jobs.chunking import chunk_job
from app.domain.jobs.extractor import JobExtraction, JobExtractor
from app.domain.jobs.ingestor import JobIngestor
from app.domain.jobs.service import JobService
from app.domain.llm.factory import get_llm_provider
from app.domain.skills.normalizer import SkillNormalizer
from app.models.job import Job
from app.worker.dead_letter import record_failure
from app.worker.tasks.resume import MAX_TRIES

__all__ = ["ingest_job"]

log = get_logger("worker.ingest_job")


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


_WORK_MODE = {"remote", "hybrid", "onsite"}
_WORK_MODE_SYNONYMS = {
    "on-site": "onsite",
    "on site": "onsite",
    "in-office": "onsite",
    "in office": "onsite",
    "office": "onsite",
    "wfh": "remote",
}
_SENIORITY = {"intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager"}
_SENIORITY_SYNONYMS = {
    "sr": "senior",
    "sr.": "senior",
    "snr": "senior",
    "jr": "junior",
    "jr.": "junior",
    "mid-level": "mid",
    "midlevel": "mid",
    "intermediate": "mid",
    "entry": "junior",
    "entry-level": "junior",
    "graduate": "junior",
    "grad": "junior",
    "principal engineer": "principal",
    "staff engineer": "staff",
    "engineering manager": "manager",
    "em": "manager",
    "tech lead": "lead",
    "team lead": "lead",
}
_SALARY_PERIOD = {"year", "month", "day", "hour"}
_SALARY_PERIOD_SYNONYMS = {
    "annual": "year",
    "annually": "year",
    "yearly": "year",
    "yr": "year",
    "pa": "year",
    "per year": "year",
    "monthly": "month",
    "mo": "month",
    "per month": "month",
    "daily": "day",
    "hourly": "hour",
    "hr": "hour",
    "per hour": "hour",
}


def _pick(value: str | None, synonyms: dict[str, str], vocab: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    key = synonyms.get(key, key)
    return key if key in vocab else None


def _currency(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    code = value.strip().upper()
    return code if len(code) == 3 and code.isascii() and code.isalpha() else None


def _normalize_enums(extraction: JobExtraction) -> JobExtraction:
    """Coerce the LLM's free-text enum fields onto the DB's CHECK vocabularies.

    ``JobExtraction`` types ``work_mode`` / ``seniority`` / ``salary_period`` /
    ``salary_currency`` as ``str | None`` and the prompt only *asks* the model
    to stay in-vocab. A drifting value ("Remote", "Sr.", "annually", "usd")
    would trip a CHECK ``IntegrityError`` in ``JobService.apply_ingestion`` and
    abort the whole ingest, so map the obvious forms and drop anything still
    out-of-vocab to ``None`` (a degrade, never a failure). Returns a copy; the
    input is not mutated.
    """
    return extraction.model_copy(
        update={
            "work_mode": _pick(extraction.work_mode, _WORK_MODE_SYNONYMS, _WORK_MODE),
            "seniority": _pick(extraction.seniority, _SENIORITY_SYNONYMS, _SENIORITY),
            "salary_period": _pick(
                extraction.salary_period, _SALARY_PERIOD_SYNONYMS, _SALARY_PERIOD
            ),
            "salary_currency": _currency(extraction.salary_currency),
        }
    )


def _resolve(raw_skills: list[Any], matches: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in raw_skills:
        m = matches.get(s.raw)
        if m is None:
            continue
        out.append(
            {
                "skill_id": str(m.skill_id),
                "slug": m.slug,
                "label": m.label,
                "weight": round(float(s.weight), 2),
            }
        )
    return out


async def ingest_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    settings = get_settings()
    redis = redis_from_settings(settings)
    channel = job_channel(job_id)
    jid = uuid.UUID(job_id)

    async with _session_for() as session:
        job = await session.get(Job, jid)
        if job is None:
            await record_failure(
                "ingest_job",
                args=(job_id,),
                kwargs={},
                error=RuntimeError(f"job {job_id} not found"),
            )
            return {"job_id": job_id, "status": "missing"}
        if job.status != "ingesting":
            return {"job_id": job_id, "status": "skipped"}

        try:
            await publish_status(
                redis, channel, resource="job", id=job_id,
                status="ingesting", message="Reading the posting…",
            )
            cleaned = JobIngestor().clean(job.raw_text)

            extractor = JobExtractor(
                get_llm_provider(settings), model=settings.llm_model_extraction
            )
            extraction = _normalize_enums(await extractor.extract(cleaned))
            await publish_status(
                redis, channel, resource="job", id=job_id,
                status="ingesting", message="Pulling out the requirements…",
            )

            embeddings = get_embeddings_provider(settings)
            normalizer = SkillNormalizer(session, embeddings)
            await normalizer.load()
            all_raw = [
                s.raw for s in (*extraction.required_skills, *extraction.preferred_skills)
            ]
            matches = await normalizer.normalize_many(all_raw)
            required = _resolve(extraction.required_skills, matches)
            preferred = _resolve(extraction.preferred_skills, matches)

            drafts = chunk_job(extraction)
            vectors = (
                await embeddings.embed_documents([d.content for d in drafts])
                if drafts
                else []
            )
            meta = {
                "model": extractor.last_usage.model if extractor.last_usage else "unknown",
                "embed_model": embeddings.model,
                "embed_dim": embeddings.dim,
                "chunks": len(drafts),
                "unmatched": sorted({r for r in all_raw if r not in matches}),
            }
            await JobService(session, settings=settings).apply_ingestion(
                jid,
                extraction=extraction,
                required=required,
                preferred=preferred,
                chunks=list(zip(drafts, vectors, strict=True)),
                meta=meta,
            )
            await session.commit()
            log.info(
                "job_ingested", job_id=job_id, chunks=len(drafts),
                required=len(required), preferred=len(preferred),
            )
            await publish_status(
                redis, channel, resource="job", id=job_id,
                status="ready", message="Ready",
            )
            return {"job_id": job_id, "status": "ready"}
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise  # transient — let ARQ retry, don't surface a terminal failure
            job = await session.get(Job, jid)
            if job is not None:
                job.status = "failed"
                job.ingest_error = "We couldn't read this job posting."
                await session.commit()
            # A Redis outage here must not swallow the dead-letter record or the
            # re-raise that drives ARQ's retry.
            with contextlib.suppress(Exception):
                await publish_status(
                    redis, channel, resource="job", id=job_id,
                    status="failed", message="We couldn't read this job posting.",
                )
            await record_failure("ingest_job", args=(job_id,), kwargs={}, error=exc)
            raise
