from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, status
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.v1.schemas.jobs import (
    JobCardOut,
    JobCreateIn,
    JobDetailOut,
    JobListOut,
    JobPatchIn,
    JobRefOut,
    JobSkillOut,
)
from app.core.db import AsyncSessionLocal
from app.core.errors import NotFoundError
from app.core.events import job_channel, sse_event, status_stream
from app.domain.jobs.service import JobFilters, JobService
from app.domain.matching.service import MatchService
from app.models.job import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _card(
    job: Job, match: tuple[float | None, str | None, str] | None = None
) -> JobCardOut:
    m_score, m_band, m_status = match if match is not None else (None, None, None)
    return JobCardOut(
        id=job.id, title=job.title, company=job.company, location=job.location,
        work_mode=job.work_mode, seniority=job.seniority, employment_type=job.employment_type,
        salary_min=job.salary_min, salary_max=job.salary_max,
        salary_currency=job.salary_currency, salary_period=job.salary_period,
        is_seed=job.is_seed, status=job.status, posted_at=job.posted_at, created_at=job.created_at,
        required_skills=[JobSkillOut(slug=s["slug"], label=s["label"], weight=s["weight"])
                        for s in job.required_skills],
        match_score=m_score, match_band=m_band, match_status=m_status,
    )


def _detail(
    job: Job, match: tuple[float | None, str | None, str] | None = None
) -> JobDetailOut:
    return JobDetailOut(
        **_card(job, match).model_dump(),
        company_domain=job.company_domain,
        experience_min_years=job.experience_min_years,
        experience_max_years=job.experience_max_years,
        description=job.description,
        responsibilities=list(job.responsibilities),
        preferred_skills=[JobSkillOut(slug=s["slug"], label=s["label"], weight=s["weight"])
                         for s in job.preferred_skills],
        raw_text=job.raw_text,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_job(body: JobCreateIn, db: DbDep, user: CurrentUser) -> JobRefOut:
    job = await JobService(db).create(user.id, raw_text=body.raw_text)
    return JobRefOut(id=job.id, status=job.status)


@router.get("")
async def list_jobs(
    db: DbDep,
    user: CurrentUser,
    q: str | None = None,
    work_mode: str | None = None,
    seniority: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    salary_min: int | None = None,
    skills: str | None = None,
    has_match: bool = False,
    sort: str = "recent",
    limit: int = 24,
    offset: int = 0,
) -> JobListOut:
    limit = max(1, min(limit, 60))
    offset = max(0, offset)
    filters = JobFilters(
        q=q,
        work_mode=work_mode,
        seniority=seniority,
        location=location,
        salary_min=salary_min,
        employment_type=employment_type,
        skills=tuple(s for s in (skills or "").split(",") if s),
        has_match=has_match,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    rows, total = await JobService(db).list_(user.id, filters)
    scores = await MatchService(db).job_scores_for(user.id, [j.id for j in rows])
    return JobListOut(
        items=[_card(j, scores.get(j.id)) for j in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{job_id}")
async def get_job(job_id: uuid.UUID, db: DbDep, user: CurrentUser) -> JobDetailOut:
    job = await JobService(db).get(user.id, job_id)
    scores = await MatchService(db).job_scores_for(user.id, [job.id])
    return _detail(job, scores.get(job.id))


@router.get("/{job_id}/events")
async def job_events(
    job_id: uuid.UUID, user: CurrentUser, redis: RedisDep
) -> EventSourceResponse:
    # Ownership check in a short-lived session (404s non-owners before streaming);
    # the request session is NOT held open for the life of the stream.
    async with AsyncSessionLocal() as session:
        await JobService(session).get(user.id, job_id)
    channel = job_channel(str(job_id))

    async def _gen() -> AsyncIterator[ServerSentEvent]:
        async for payload in status_stream(
            redis, channel, terminal={"ready", "failed"}
        ):
            if payload.get("event") == "open":
                # Read the current status only after the subscription is live so a
                # transition between the read and the subscribe cannot be missed.
                try:
                    async with AsyncSessionLocal() as s:
                        current = (await JobService(s).get(user.id, job_id)).status
                except NotFoundError:
                    return  # deleted mid-stream — close cleanly
                yield sse_event(
                    {
                        "event": "status",
                        "resource": "job",
                        "id": str(job_id),
                        "status": current,
                    }
                )
                if current in {"ready", "failed"}:
                    yield sse_event({"event": "done", "status": current, "totals": {}})
                    return
                continue
            yield sse_event(payload)

    return EventSourceResponse(_gen())


@router.patch("/{job_id}")
async def patch_job(
    job_id: uuid.UUID, body: JobPatchIn, db: DbDep, user: CurrentUser
) -> JobDetailOut:
    job = await JobService(db).update(user.id, job_id, title=body.title)
    return _detail(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
    await JobService(db).delete(user.id, job_id)
