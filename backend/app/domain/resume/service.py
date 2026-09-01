from __future__ import annotations

import contextlib
import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

import filetype  # type: ignore[import-untyped]
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.logging import current_request_id
from app.core.queue import enqueue
from app.domain.profile.service import SUBENTITY_MODELS, ProfileService
from app.domain.resume.extractor import ResumeExtraction
from app.infra.storage.base import FileStore
from app.infra.storage.factory import get_file_store
from app.models.resume import Resume

# Destination column widths for the profile sub-entity string fields. A long LLM
# value must be clamped before the merge or asyncpg raises StringDataRightTruncation.
_SUBENTITY_MAXLEN: dict[str, int] = {
    "company": 200, "title": 200, "employment_type": 40, "location": 200,
    "institution": 200, "degree": 200, "field": 200, "grade": 80,
    "name": 200, "url": 300, "issuer": 200, "credential_id": 200,
}


def _clamp_row(data: dict[str, Any]) -> dict[str, Any]:
    return {
        k: (v[: _SUBENTITY_MAXLEN[k]] if isinstance(v, str) and k in _SUBENTITY_MAXLEN else v)
        for k, v in data.items()
    }


class ResumeService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        file_store: FileStore | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.file_store = file_store or get_file_store(self.settings)

    async def _audit(
        self,
        action: str,
        user_id: uuid.UUID,
        *,
        resource_id: uuid.UUID | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        await audit(
            self.session,
            actor_type="user",
            action=action,
            actor_user_id=user_id,
            resource_type="resume",
            resource_id=resource_id,
            request_id=current_request_id(),
            meta=meta,
        )

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        filename: str,
        data: bytes,
        declared_content_type: str,
    ) -> Resume:
        kind = filetype.guess(data)
        if kind is None or kind.mime != "application/pdf":
            raise ValidationAppError(code="resume.not_pdf")
        if len(data) > self.settings.resume_max_bytes:
            raise ValidationAppError(code="resume.too_large")

        resume_id = uuid.uuid4()
        key = f"resumes/{user_id}/{resume_id}.pdf"
        await self.file_store.put(key, data, content_type="application/pdf")

        count = await self.session.scalar(
            select(func.count())
            .select_from(Resume)
            .where(Resume.user_id == user_id, Resume.deleted_at.is_(None))
        )
        is_primary = (count or 0) == 0

        resume = Resume(
            id=resume_id,
            user_id=user_id,
            title=filename[:200],
            original_filename=filename[:300],
            file_ref=key,
            content_type="application/pdf",
            size_bytes=len(data),
            status="uploaded",
            is_primary=is_primary,
        )
        self.session.add(resume)
        await self.session.flush()

        # Defer so the request transaction commits before the worker picks it up;
        # a stable _job_id makes a duplicate enqueue a no-op (see core.queue).
        await enqueue(
            "parse_resume", str(resume_id), _defer_by=2.0, _job_id=f"parse:{resume_id}"
        )
        await self._audit(
            "resume.upload",
            user_id,
            resource_id=resume_id,
            meta={"filename": filename, "size_bytes": len(data)},
        )
        return resume

    async def get(self, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
        resume = await self.session.get(Resume, resume_id)
        if resume is None or resume.user_id != user_id or resume.deleted_at is not None:
            raise NotFoundError(detail="Resume not found")
        return resume

    async def list_(self, user_id: uuid.UUID) -> list[Resume]:
        result = await self.session.execute(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.deleted_at.is_(None))
            .order_by(Resume.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(
        self,
        user_id: uuid.UUID,
        resume_id: uuid.UUID,
        *,
        title: str | None = None,
        is_primary: bool | None = None,
    ) -> Resume:
        resume = await self.get(user_id, resume_id)
        if title is not None:
            resume.title = title[:200]
        if is_primary is True:
            await self.session.execute(
                update(Resume)
                .where(
                    Resume.user_id == user_id,
                    Resume.id != resume_id,
                    Resume.is_primary.is_(True),
                    Resume.deleted_at.is_(None),
                )
                .values(is_primary=False)
            )
            resume.is_primary = True
        elif is_primary is False:
            resume.is_primary = False
        await self.session.flush()
        return resume

    async def delete(self, user_id: uuid.UUID, resume_id: uuid.UUID) -> None:
        resume = await self.get(user_id, resume_id)
        resume.deleted_at = dt.datetime.now(dt.UTC)
        with contextlib.suppress(Exception):
            await self.file_store.delete(resume.file_ref)
        await self.session.flush()
        await self._audit("resume.delete", user_id, resource_id=resume_id)

    async def reprocess(self, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
        resume = await self.get(user_id, resume_id)
        resume.status = "uploaded"
        resume.parse_error = None
        await self.session.flush()
        await enqueue(
            "parse_resume", str(resume_id), _defer_by=2.0, _job_id=f"parse:{resume_id}"
        )
        await self._audit("resume.reprocess", user_id, resource_id=resume_id)
        return resume

    async def confirm_profile(
        self, user_id: uuid.UUID, resume_id: uuid.UUID, extraction: ResumeExtraction
    ) -> None:
        resume = await self.get(user_id, resume_id)
        if resume.status != "extracted":
            raise ConflictError(code="resume.not_extracted")

        ps = ProfileService(self.session)
        profile = await ps.get_or_create(user_id)

        scalars: dict[str, str | None] = {
            "location": extraction.location,
            "github_url": extraction.github_url,
            "linkedin_url": extraction.linkedin_url,
            "portfolio_url": extraction.portfolio_url,
            "career_goals": extraction.summary,
        }
        # Clamp to the CareerProfile column widths so a long LLM value can't raise
        # StringDataRightTruncation mid-merge (career_goals is TEXT — no limit).
        maxlen = {"location": 200, "github_url": 300, "linkedin_url": 300, "portfolio_url": 300}
        for col, val in scalars.items():
            if val:
                limit = maxlen.get(col)
                setattr(profile, col, val[:limit] if limit else val)

        # Every ``*_date`` field is deliberately excluded: the extracted values are
        # free-text strings while the DB columns are SQL ``Date``. Date normalisation
        # is Phase 3; the raw strings stay available in ``resume.extraction``.
        merge_plan: list[tuple[str, Sequence[BaseModel], set[str]]] = [
            (
                "experiences",
                extraction.experiences,
                {
                    "company", "title", "employment_type", "is_current",
                    "location", "description", "highlights", "tech",
                },
            ),
            (
                "education",
                extraction.education,
                {"institution", "degree", "field", "grade"},
            ),
            (
                "projects",
                extraction.projects,
                {"name", "description", "url", "highlights", "tech"},
            ),
            (
                "certifications",
                extraction.certifications,
                {"name", "issuer", "credential_id", "url"},
            ),
        ]
        for section, items, field_set in merge_plan:
            model = SUBENTITY_MODELS[section]
            await self.session.execute(
                delete(model).where(
                    model.user_id == user_id,  # type: ignore[attr-defined]
                    model.source == "resume_extraction",  # type: ignore[attr-defined]
                )
            )
            base = await self.session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.profile_id == profile.id)  # type: ignore[attr-defined]
            )
            for i, item in enumerate(items):
                self.session.add(
                    model(
                        user_id=user_id,
                        profile_id=profile.id,
                        source="resume_extraction",
                        order_index=(base or 0) + i,
                        **_clamp_row(item.model_dump(include=field_set)),
                    )
                )

        await self.session.flush()
        await ps._recompute(profile)

        resume.confirmed_at = dt.datetime.now(dt.UTC)
        await self.session.flush()

        await self._audit(
            "resume.confirm_profile",
            user_id,
            resource_id=resume_id,
            meta={
                "resume_id": str(resume_id),
                "counts": {
                    "experiences": len(extraction.experiences),
                    "education": len(extraction.education),
                    "projects": len(extraction.projects),
                    "certifications": len(extraction.certifications),
                },
            },
        )
