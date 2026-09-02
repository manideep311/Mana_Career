from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, cast, delete, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import current_request_id
from app.core.queue import enqueue
from app.domain.jobs.chunking import JobChunkDraft
from app.domain.jobs.extractor import JobExtraction
from app.models.job import Job, JobChunk

_MIN_RAW = 40
_MAXLEN = {"title": 300, "company": 200, "location": 200, "company_domain": 200}


@dataclass(frozen=True)
class JobFilters:
    q: str | None = None
    work_mode: str | None = None
    seniority: str | None = None
    location: str | None = None
    salary_min: int | None = None
    employment_type: str | None = None
    skills: tuple[str, ...] = ()
    sort: str = "recent"
    limit: int = 24
    offset: int = 0


class JobService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def _audit(
        self, action: str, user_id: uuid.UUID, *,
        resource_id: uuid.UUID | None = None, meta: dict[str, Any] | None = None,
    ) -> None:
        await audit(self.session, actor_type="user", action=action, actor_user_id=user_id,
                    resource_type="job", resource_id=resource_id,
                    request_id=current_request_id(), meta=meta)

    async def create(self, user_id: uuid.UUID, *, raw_text: str) -> Job:
        cleaned = raw_text.strip()
        if len(cleaned) < _MIN_RAW:
            raise ValidationAppError(code="job.empty")
        job = Job(user_id=user_id, raw_text=cleaned, source="user_paste", status="ingesting")
        self.session.add(job)
        await self.session.flush()
        await enqueue("ingest_job", str(job.id), _defer_by=2.0, _job_id=f"ingest_job:{job.id}")
        await self._audit("job.create", user_id, resource_id=job.id)
        return job

    def _visible(self, user_id: uuid.UUID) -> Any:
        return or_(Job.user_id == user_id, Job.user_id.is_(None))

    async def get(self, user_id: uuid.UUID, job_id: uuid.UUID) -> Job:
        row = (await self.session.execute(
            select(Job).where(Job.id == job_id, Job.deleted_at.is_(None), self._visible(user_id))
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError(detail="Job not found")
        return row

    async def _owned(self, user_id: uuid.UUID, job_id: uuid.UUID) -> Job:
        row = (await self.session.execute(
            select(Job).where(Job.id == job_id, Job.user_id == user_id, Job.deleted_at.is_(None))
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError(detail="Job not found")
        return row

    def _filtered(self, user_id: uuid.UUID, f: JobFilters) -> Select[tuple[Job]]:
        stmt = select(Job).where(
            self._visible(user_id), Job.deleted_at.is_(None), Job.status == "ready"
        )
        if f.q:
            stmt = stmt.where(
                Job.search_tsv.op("@@")(func.websearch_to_tsquery("english", f.q))
                | Job.title.ilike(f"%{f.q}%")
                | Job.company.ilike(f"%{f.q}%")
            )
        if f.work_mode:
            stmt = stmt.where(Job.work_mode == f.work_mode)
        if f.seniority:
            stmt = stmt.where(Job.seniority == f.seniority)
        if f.employment_type:
            stmt = stmt.where(Job.employment_type == f.employment_type)
        if f.location:
            stmt = stmt.where(Job.location.ilike(f"%{f.location}%"))
        if f.salary_min is not None:
            stmt = stmt.where(or_(Job.salary_max >= f.salary_min, Job.salary_max.is_(None)))
        for slug in f.skills:
            stmt = stmt.where(Job.required_skills.op("@>")(cast([{"slug": slug}], JSONB)))
        return stmt

    async def list_(self, user_id: uuid.UUID, f: JobFilters) -> tuple[list[Job], int]:
        stmt = self._filtered(user_id, f)
        total = (await self.session.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            stmt.order_by(Job.created_at.desc()).limit(f.limit).offset(f.offset)
        )).scalars().all()
        return list(rows), int(total)

    async def update(self, user_id: uuid.UUID, job_id: uuid.UUID, *, title: str | None) -> Job:
        job = await self._owned(user_id, job_id)
        if title is not None:
            job.title = title[:_MAXLEN["title"]]
        await self.session.flush()
        return job

    async def delete(self, user_id: uuid.UUID, job_id: uuid.UUID) -> None:
        job = await self._owned(user_id, job_id)
        job.deleted_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        await self._audit("job.delete", user_id, resource_id=job_id)

    async def apply_ingestion(
        self, job_id: uuid.UUID, *, extraction: JobExtraction,
        required: list[dict[str, Any]], preferred: list[dict[str, Any]],
        chunks: Sequence[tuple[JobChunkDraft, list[float]]], meta: dict[str, Any],
    ) -> None:
        job = await self.session.get(Job, job_id)
        if job is None:
            raise NotFoundError(detail="Job not found")
        for col in ("company", "company_domain", "location", "work_mode", "employment_type",
                    "seniority", "experience_min_years", "experience_max_years",
                    "salary_min", "salary_max", "salary_currency", "salary_period", "description"):
            val = getattr(extraction, col)
            if isinstance(val, str) and col in _MAXLEN:
                val = val[: _MAXLEN[col]]
            setattr(job, col, val)
        if extraction.title:
            job.title = extraction.title[:_MAXLEN["title"]]
        job.responsibilities = list(extraction.responsibilities)
        job.required_skills = required
        job.preferred_skills = preferred
        job.structured = extraction.model_dump()
        job.extraction_meta = meta
        job.salary_source = "jd" if (extraction.salary_min or extraction.salary_max) else None
        job.status = "ready"
        job.ingest_error = None
        await self.session.execute(
            delete(JobChunk).where(JobChunk.job_id == job_id)
        )
        for draft, vec in chunks:
            self.session.add(JobChunk(
                job_id=job_id, owner_id=job.user_id, chunk_index=draft.chunk_index,
                section=draft.section, content=draft.content, token_count=draft.token_count,
                embed_model=meta["embed_model"], embed_dim=meta["embed_dim"], embedding=vec,
            ))
        await self.session.flush()
