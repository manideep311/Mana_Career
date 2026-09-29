"""Safety net: nothing stays in an in-progress state forever.

Retries (``app.worker.retry``) handle failures a worker can see. This cron job
handles the ones it can't — a worker killed mid-job, a job lost from Redis, a
deploy that dropped the queue. Anything still "in progress" long after its
worst-case runtime (3 tries x 300 s job timeout + backoff ≈ 16 min) is moved
to an explicit failure state and its live stream is told so.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.events import job_channel, publish_status, resume_channel, roadmap_channel
from app.core.logging import get_logger
from app.core.redis import redis_from_settings
from app.models.ai import AiSession
from app.models.job import Job
from app.models.learning import LearningRecommendation
from app.models.match import JobMatch
from app.models.resume import Resume

log = get_logger("worker.sweeper")

STALE_AFTER = dt.timedelta(minutes=20)

RESUME_IN_PROGRESS = ("uploaded", "parsing", "parsed", "extracting")
RESUME_MESSAGE = "This took longer than it should. Please upload your résumé again."
JOB_MESSAGE = "We couldn't finish reading this job posting. Please add it again."
MATCH_MESSAGE = "Scoring didn't finish. Try refreshing the match."
AGENT_MESSAGE = "This run stopped responding and was ended."
ROADMAP_MESSAGE = "Roadmap planning didn't finish. Please try again."


@contextlib.asynccontextmanager
async def _session_for() -> AsyncIterator[AsyncSession]:
    """Session seam (DB tests swap in their rolled-back session)."""
    async with AsyncSessionLocal() as session:
        yield session


async def sweep_stuck_jobs(
    ctx: dict[str, Any], now: dt.datetime | None = None
) -> dict[str, int]:
    now = now or dt.datetime.now(dt.UTC)
    cutoff = now - STALE_AFTER
    events: list[tuple[str, dict[str, Any]]] = []
    counts = {"resumes": 0, "jobs": 0, "matches": 0, "agent_runs": 0, "roadmaps": 0}

    async with _session_for() as session:
        # SKIP LOCKED: never wait on (or fight) a worker that is mid-update.
        resumes = (
            await session.execute(
                select(Resume)
                .where(Resume.status.in_(RESUME_IN_PROGRESS), Resume.updated_at < cutoff)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for r in resumes:
            r.status = "failed"
            r.parse_error = RESUME_MESSAGE
            events.append((resume_channel(str(r.id)), _status("resume", r.id, RESUME_MESSAGE)))
        counts["resumes"] = len(resumes)

        jobs = (
            await session.execute(
                select(Job)
                .where(Job.status == "ingesting", Job.updated_at < cutoff)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for j in jobs:
            j.status = "failed"
            j.ingest_error = JOB_MESSAGE
            events.append((job_channel(str(j.id)), _status("job", j.id, JOB_MESSAGE)))
        counts["jobs"] = len(jobs)

        matches = (
            await session.execute(
                select(JobMatch)
                .where(JobMatch.status == "scoring", JobMatch.updated_at < cutoff)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for m in matches:
            m.status = "failed"
            m.error = MATCH_MESSAGE
        counts["matches"] = len(matches)

        runs = (
            await session.execute(
                select(AiSession)
                .where(AiSession.status == "running", AiSession.updated_at < cutoff)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for s in runs:
            s.status = "error"
            s.error = AGENT_MESSAGE
            s.ended_at = now
            if s.run_id:
                channel = f"sse:ai:{s.run_id}"
                events.append((channel, {"event": "error", "message": AGENT_MESSAGE}))
                events.append((channel, {"event": "done", "status": "error", "totals": {}}))
        counts["agent_runs"] = len(runs)

        roadmaps = (
            await session.execute(
                select(LearningRecommendation)
                .where(
                    LearningRecommendation.status == "planning",
                    LearningRecommendation.updated_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for rec in roadmaps:
            rec.status = "archived"
            events.append(
                (
                    roadmap_channel(str(rec.id)),
                    {"event": "error", "status": "archived", "message": ROADMAP_MESSAGE},
                )
            )
        counts["roadmaps"] = len(roadmaps)

        await session.commit()

    if any(counts.values()):
        log.warning("stuck_jobs_failed", **counts)
        await _publish(events)
    return counts


def _status(resource: str, rid: Any, message: str) -> dict[str, Any]:
    return {"event": "status", "resource": resource, "id": str(rid), "status": "failed",
            "message": message}


async def _publish(events: list[tuple[str, dict[str, Any]]]) -> None:
    """Best effort: the DB already holds the truth; streams are a courtesy."""
    redis = redis_from_settings(get_settings())
    try:
        for channel, payload in events:
            with contextlib.suppress(Exception):
                if payload.get("event") == "status":
                    await publish_status(
                        redis,
                        channel,
                        resource=payload["resource"],
                        id=payload["id"],
                        status="failed",
                        message=payload["message"],
                    )
                else:
                    await redis.publish(channel, json.dumps(payload))
    finally:
        with contextlib.suppress(Exception):
            await redis.aclose()
