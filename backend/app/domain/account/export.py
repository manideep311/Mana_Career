"""Everything a person has put into Mana Career, as one ZIP they can keep.

``mana-career-data.json`` holds their rows (profile, résumés and what was read
from them, applications with letters and emails, roadmaps, Mana AI
conversations, …) and ``resumes/`` holds the PDFs they uploaded. Every query is
scoped to the one user; secrets and internal plumbing (password and token
hashes, search vectors, model metadata) are never included.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import uuid
import zipfile
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.storage.base import FileStore
from app.models.ai import AiAction, AiSession, Message
from app.models.application import Application, ApplicationEmail, CoverLetter
from app.models.application_event import ApplicationEvent
from app.models.job import Job
from app.models.learning import LearningRecommendation, RoadmapMilestone
from app.models.match import JobMatch, SkillGap
from app.models.profile import (
    CareerProfile,
    ProfileCertification,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
)
from app.models.resume import Resume
from app.models.resume_version import ResumeSuggestion, ResumeVersion
from app.models.skill import ProfileSkill, Skill
from app.models.user import User

log = get_logger("account.export")

# Never exported: secrets, search internals, and bookkeeping about the model
# calls. `user_id` is dropped as redundant (it's all one person's data).
_DENY = frozenset(
    {"password_hash", "token_hash", "embedding", "search_tsv", "payload_hash", "user_id"}
)

_README = """Your Mana Career data
=====================

mana-career-data.json   Everything you added or that was created for you:
                        account, profile, skills, résumés (with the text we
                        read from them), tailored versions, saved jobs, job
                        matches, applications (letters, emails, timeline),
                        roadmaps, and your Mana AI conversations.
resumes/                The résumé PDFs you uploaded.

Not included: your password (only a one-way hash is ever stored), sign-in
tokens, search indexes and internal processing details.
"""


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    return value


def serialize(row: Any) -> dict[str, Any]:
    """A row's columns as JSON-safe values, minus the deny list."""
    out: dict[str, Any] = {}
    for attr in sa_inspect(row).mapper.column_attrs:
        key = attr.key
        if key in _DENY or key.endswith("_meta"):
            continue
        out[key] = _plain(getattr(row, key))
    return out


def build_zip(data: dict[str, Any], files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "mana-career-data.json",
            json.dumps(data, indent=2, ensure_ascii=False, default=_plain),
        )
        z.writestr("README.txt", _README)
        for name, blob in files.items():
            z.writestr(name, blob)
    return buf.getvalue()


def _pdf_name(resume: Resume, taken: set[str]) -> str:
    base = re.sub(r"[^\w .-]", "", resume.original_filename or "").strip() or str(resume.id)
    base = base[:-4] if base.lower().endswith(".pdf") else base
    name, n = f"resumes/{base}.pdf", 2
    while name in taken:
        name, n = f"resumes/{base} ({n}).pdf", n + 1
    taken.add(name)
    return name


class AccountExporter:
    def __init__(self, session: AsyncSession, store: FileStore) -> None:
        self._s = session
        self._store = store

    async def _rows(self, model: Any, user_id: uuid.UUID, *order: Any) -> list[dict[str, Any]]:
        stmt = select(model).where(model.user_id == user_id)
        if order:
            stmt = stmt.order_by(*order)
        return [serialize(r) for r in (await self._s.execute(stmt)).scalars().all()]

    async def collect(self, user: User) -> tuple[dict[str, Any], dict[str, bytes]]:
        uid = user.id
        profile = (
            await self._s.execute(select(CareerProfile).where(CareerProfile.user_id == uid))
        ).scalar_one_or_none()
        skills = (
            await self._s.execute(
                select(ProfileSkill, Skill)
                .join(Skill, Skill.id == ProfileSkill.skill_id)
                .where(ProfileSkill.user_id == uid)
            )
        ).all()
        resumes = (
            await self._s.execute(
                select(Resume).where(Resume.user_id == uid).order_by(Resume.created_at)
            )
        ).scalars().all()

        files: dict[str, bytes] = {}
        taken: set[str] = set()
        resume_rows = []
        for resume in resumes:
            row = serialize(resume)
            try:
                blob = await self._store.get(resume.file_ref)
            except Exception:  # a missing file mustn't block the rest of the export
                log.warning("export_resume_file_missing", resume_id=str(resume.id))
                row["file_in_export"] = None
            else:
                name = _pdf_name(resume, taken)
                files[name] = blob
                row["file_in_export"] = name
            resume_rows.append(row)

        data: dict[str, Any] = {
            "exported_at": dt.datetime.now(dt.UTC).isoformat(),
            "account": {
                "email": user.email,
                "full_name": user.full_name,
                "email_verified": user.email_verified,
                "created_at": _plain(user.created_at),
            },
            "profile": serialize(profile) if profile else None,
            "experiences": await self._rows(ProfileExperience, uid, ProfileExperience.order_index),
            "education": await self._rows(ProfileEducation, uid, ProfileEducation.order_index),
            "projects": await self._rows(ProfileProject, uid, ProfileProject.order_index),
            "certifications": await self._rows(
                ProfileCertification, uid, ProfileCertification.order_index
            ),
            "skills": [
                {
                    **serialize(ps),
                    "skill": {"slug": s.slug, "label": s.label, "category": s.category},
                }
                for ps, s in skills
            ],
            "resumes": resume_rows,
            "resume_versions": await self._rows(ResumeVersion, uid, ResumeVersion.created_at),
            "resume_suggestions": await self._rows(ResumeSuggestion, uid),
            "saved_jobs": await self._rows(Job, uid, Job.created_at),
            "job_matches": await self._rows(JobMatch, uid),
            "skill_gaps": await self._rows(SkillGap, uid),
            "applications": await self._rows(Application, uid, Application.created_at),
            "cover_letters": await self._rows(CoverLetter, uid, CoverLetter.created_at),
            "application_emails": await self._rows(ApplicationEmail, uid),
            "application_events": await self._rows(ApplicationEvent, uid),
            "roadmaps": await self._rows(LearningRecommendation, uid),
            "roadmap_milestones": await self._rows(RoadmapMilestone, uid),
            "mana_ai_sessions": await self._rows(AiSession, uid, AiSession.created_at),
            "mana_ai_messages": await self._rows(Message, uid, Message.created_at),
            "mana_ai_activity": await self._rows(AiAction, uid),
        }
        return data, files

    async def export(self, user: User) -> tuple[str, bytes]:
        data, files = await self.collect(user)
        filename = f"mana-career-export-{dt.datetime.now(dt.UTC):%Y-%m-%d}.zip"
        return filename, build_zip(data, files)
