from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.events import publish_status, resume_channel
from app.core.queue import enqueue
from app.core.redis import redis_from_settings
from app.domain.llm.factory import get_llm_provider
from app.domain.resume.extractor import ResumeExtractor
from app.domain.resume.parser import (
    MIN_DIGITAL_TEXT_CHARS,
    SCANNED_PDF_MESSAGE,
    PypdfResumeParser,
)
from app.infra.storage.factory import get_file_store
from app.models.resume import Resume
from app.worker.dead_letter import record_failure

# Keep in sync with ``WorkerSettings.max_tries`` (app/worker/main.py imports this).
MAX_TRIES = 3

__all__ = ["MAX_TRIES", "extract_resume", "parse_resume"]


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


async def parse_resume(ctx: dict[str, Any], resume_id: str) -> dict[str, Any]:
    settings = get_settings()
    redis = redis_from_settings(settings)
    channel = resume_channel(resume_id)
    rid = uuid.UUID(resume_id)

    async with _session_for() as session:
        resume = await session.get(Resume, rid)
        if resume is None:
            await record_failure(
                "parse_resume",
                args=(resume_id,),
                kwargs={},
                error=RuntimeError(f"resume {resume_id} not found (lost job or deleted)"),
            )
            return {"resume_id": resume_id, "status": "missing"}
        if resume.status not in {"uploaded", "parsing"}:
            # Skip only when the résumé has genuinely moved past this stage
            # (parsed/extracting/extracted/failed). "parsing" is admitted so an
            # ARQ retry — which re-enters from the top after the first attempt
            # already committed status="parsing" — can actually run. Concurrent
            # duplicates are prevented upstream by the _job_id dedup.
            return {"resume_id": resume_id, "status": "skipped"}

        try:
            resume.status = "parsing"
            await session.commit()
            await publish_status(
                redis,
                channel,
                resource="resume",
                id=resume_id,
                status="parsing",
                message="Reading your résumé…",
            )

            data = await get_file_store(settings).get(resume.file_ref)
            parsed = await PypdfResumeParser().parse(data)

            if parsed.page_count > settings.resume_max_pages:
                message = (
                    f"This résumé has {parsed.page_count} pages; "
                    f"the limit is {settings.resume_max_pages}."
                )
                resume.status = "failed"
                resume.parse_error = message
                await session.commit()
                await publish_status(
                    redis,
                    channel,
                    resource="resume",
                    id=resume_id,
                    status="failed",
                    message=message,
                )
                return {"resume_id": resume_id, "status": "failed"}

            if len(parsed.text) < MIN_DIGITAL_TEXT_CHARS:
                message = SCANNED_PDF_MESSAGE
                resume.status = "failed"
                resume.parse_error = message
                await session.commit()
                await publish_status(
                    redis,
                    channel,
                    resource="resume",
                    id=resume_id,
                    status="failed",
                    message=message,
                )
                return {"resume_id": resume_id, "status": "failed"}

            resume.extracted_text = parsed.text
            resume.page_count = parsed.page_count
            resume.status = "parsed"
            await session.commit()
            await publish_status(
                redis,
                channel,
                resource="resume",
                id=resume_id,
                status="parsed",
                message="Got it — pulling out the details…",
            )
            await enqueue("extract_resume", resume_id)
            return {"resume_id": resume_id, "status": "parsed"}
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise  # let ARQ retry; don't surface a terminal failure on a transient error
            resume = await session.get(Resume, rid)
            if resume is not None:
                resume.status = "failed"
                resume.parse_error = "We couldn't read this file."
                await session.commit()
            # A Redis outage here must not swallow the dead-letter record or the
            # re-raise that drives ARQ's retry.
            with contextlib.suppress(Exception):
                await publish_status(
                    redis,
                    channel,
                    resource="resume",
                    id=resume_id,
                    status="failed",
                    message="We couldn't read this file.",
                )
            await record_failure("parse_resume", args=(resume_id,), kwargs={}, error=exc)
            raise


async def extract_resume(ctx: dict[str, Any], resume_id: str) -> dict[str, Any]:
    settings = get_settings()
    redis = redis_from_settings(settings)
    channel = resume_channel(resume_id)
    rid = uuid.UUID(resume_id)

    async with _session_for() as session:
        resume = await session.get(Resume, rid)
        if resume is None:
            await record_failure(
                "extract_resume",
                args=(resume_id,),
                kwargs={},
                error=RuntimeError(f"resume {resume_id} not found (lost job or deleted)"),
            )
            return {"resume_id": resume_id, "status": "missing"}
        if resume.status not in {"parsed", "extracting"}:
            # Skip only when the résumé has genuinely moved past this stage.
            # "extracting" is admitted so an ARQ retry can re-run (see parse_resume).
            return {"resume_id": resume_id, "status": "skipped"}

        try:
            resume.status = "extracting"
            await session.commit()
            await publish_status(
                redis,
                channel,
                resource="resume",
                id=resume_id,
                status="extracting",
                message="Making sense of your experience…",
            )

            extractor = ResumeExtractor(
                get_llm_provider(settings), model=settings.llm_model_extraction
            )
            extraction = await extractor.extract(resume.extracted_text or "")

            resume.extraction = extraction.model_dump()
            resume.status = "extracted"
            await session.commit()
            await publish_status(
                redis,
                channel,
                resource="resume",
                id=resume_id,
                status="extracted",
                message="Ready to review",
            )
            return {"resume_id": resume_id, "status": "extracted"}
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise  # let ARQ retry; don't surface a terminal failure on a transient error
            resume = await session.get(Resume, rid)
            if resume is not None:
                resume.status = "failed"
                resume.parse_error = "We couldn't understand this résumé. Try re-uploading."
                await session.commit()
            # A Redis outage here must not swallow the dead-letter record or the
            # re-raise that drives ARQ's retry.
            with contextlib.suppress(Exception):
                await publish_status(
                    redis,
                    channel,
                    resource="resume",
                    id=resume_id,
                    status="failed",
                    message="We couldn't understand this résumé. Try re-uploading.",
                )
            await record_failure("extract_resume", args=(resume_id,), kwargs={}, error=exc)
            raise
