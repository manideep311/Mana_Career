"""``TailoringService`` -- session-scoped CRUD over ``ResumeVersion`` rows,
plus a deterministic, pure field-level diff between two ``ResumeExtraction``s.

The diff is intentionally side-effect free: it never touches the database and
never calls an LLM. It is the primitive `TailoringService` (and later, the
tailoring API) uses to explain what an AI-tailored version changed relative
to its parent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.domain.resume.extractor import ResumeExtraction
from app.models.resume import Resume
from app.models.resume_version import ResumeVersion

DeltaOp = Literal["added", "removed", "changed", "reordered"]


@dataclass(frozen=True)
class FieldDelta:
    path: str
    op: DeltaOp
    before: Any
    after: Any


@dataclass(frozen=True)
class ResumeDiff:
    deltas: list[FieldDelta]

    def as_dict(self) -> dict[str, Any]:
        return {
            "deltas": [
                {
                    "path": d.path,
                    "op": d.op,
                    "before": d.before,
                    "after": d.after,
                }
                for d in self.deltas
            ]
        }


# Top-level scalar fields compared directly with ``!=``.
_SCALAR_FIELDS = (
    "full_name", "email", "location",
    "github_url", "linkedin_url", "portfolio_url", "summary",
)

# (section attr, key fields, sub-scalar fields, sub-list fields)
_SUB_SECTIONS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "experiences", ("company", "title"),
        ("employment_type", "start_date", "end_date", "is_current", "location", "description"),
        ("highlights", "tech"),
    ),
    (
        "projects", ("name",),
        ("description", "url", "start_date", "end_date"),
        ("highlights", "tech"),
    ),
    (
        "education", ("institution", "degree"),
        ("field", "start_date", "end_date", "grade"),
        (),
    ),
    (
        "certifications", ("name",),
        ("issuer", "issued_date", "expires_date", "credential_id", "url"),
        (),
    ),
)


def _diff_list(path: str, before: list[str], after: list[str]) -> list[FieldDelta]:
    """Set-based diff of two string lists sharing one ``path``.

    - same multiset of items, different order -> one ``reordered`` delta
    - after adds items relative to before -> one ``added`` delta
    - before has items missing from after -> one ``removed`` delta
    - both -> both deltas (in that order)
    - identical lists -> ``[]``
    """
    if before == after:
        return []
    if sorted(before) == sorted(after):
        return [FieldDelta(path=path, op="reordered", before=before, after=after)]
    deltas: list[FieldDelta] = []
    added = [x for x in after if x not in before]
    removed = [x for x in before if x not in after]
    if added:
        deltas.append(FieldDelta(path=path, op="added", before=None, after=added))
    if removed:
        deltas.append(FieldDelta(path=path, op="removed", before=removed, after=None))
    return deltas


def _key_of(entry: Any, key_fields: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(getattr(entry, f) for f in key_fields)


def _diff_section(
    section: str,
    key_fields: tuple[str, ...],
    scalar_fields: tuple[str, ...],
    list_fields: tuple[str, ...],
    base_entries: list[Any],
    other_entries: list[Any],
) -> list[FieldDelta]:
    base_by_key = {_key_of(e, key_fields): (i, e) for i, e in enumerate(base_entries)}
    other_by_key = {_key_of(e, key_fields): (i, e) for i, e in enumerate(other_entries)}

    deltas: list[FieldDelta] = []
    for key, (other_index, other_entry) in other_by_key.items():
        match = base_by_key.get(key)
        if match is None:
            deltas.append(
                FieldDelta(
                    path=f"{section}[{other_index}]",
                    op="added",
                    before=None,
                    after=other_entry.model_dump(mode="json"),
                )
            )
            continue
        _base_index, base_entry = match
        entry_path = f"{section}[{other_index}]"
        for field in scalar_fields:
            old = getattr(base_entry, field)
            new = getattr(other_entry, field)
            if old != new:
                deltas.append(
                    FieldDelta(path=f"{entry_path}.{field}", op="changed", before=old, after=new)
                )
        for field in list_fields:
            deltas.extend(
                _diff_list(
                    f"{entry_path}.{field}", getattr(base_entry, field), getattr(other_entry, field)
                )
            )

    for key, (base_index, base_entry) in base_by_key.items():
        if key not in other_by_key:
            deltas.append(
                FieldDelta(
                    path=f"{section}[{base_index}]",
                    op="removed",
                    before=base_entry.model_dump(mode="json"),
                    after=None,
                )
            )
    return deltas


def diff(base: ResumeExtraction, other: ResumeExtraction) -> ResumeDiff:
    """Deterministic, pure field-level diff between two ``ResumeExtraction``s."""
    deltas: list[FieldDelta] = []

    for field in _SCALAR_FIELDS:
        old = getattr(base, field)
        new = getattr(other, field)
        if old != new:
            deltas.append(FieldDelta(path=field, op="changed", before=old, after=new))

    deltas.extend(_diff_list("skills", base.skills, other.skills))

    for section, key_fields, scalar_fields, list_fields in _SUB_SECTIONS:
        deltas.extend(
            _diff_section(
                section, key_fields, scalar_fields, list_fields,
                getattr(base, section), getattr(other, section),
            )
        )

    return ResumeDiff(deltas=deltas)


class TailoringService:
    """Session-scoped CRUD over ``ResumeVersion`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_base_snapshot(
        self, user_id: uuid.UUID, resume_id: uuid.UUID
    ) -> ResumeVersion:
        """Idempotently return the ``base_snapshot`` version for a résumé,
        creating it from ``Resume.extraction`` if it doesn't exist yet."""
        existing = (await self.session.execute(
            select(ResumeVersion).where(
                ResumeVersion.resume_id == resume_id,
                ResumeVersion.user_id == user_id,
                ResumeVersion.kind == "base_snapshot",
            )
        )).scalar_one_or_none()
        if existing is not None:
            return existing

        resume = (await self.session.execute(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        )).scalar_one_or_none()
        if resume is None:
            raise NotFoundError(detail="Resume not found")

        version = ResumeVersion(
            user_id=user_id,
            resume_id=resume_id,
            kind="base_snapshot",
            content=resume.extraction or {},
            created_by="user",
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def write_version(
        self,
        *,
        user_id: uuid.UUID,
        resume_id: uuid.UUID,
        job_id: uuid.UUID | None,
        parent_version_id: uuid.UUID | None,
        kind: str,
        content: dict[str, Any],
        generation_meta: dict[str, Any],
        label: str | None = None,
        created_by: str,
    ) -> ResumeVersion:
        version = ResumeVersion(
            user_id=user_id,
            resume_id=resume_id,
            job_id=job_id,
            parent_version_id=parent_version_id,
            kind=kind,
            content=content,
            generation_meta=generation_meta,
            label=label,
            created_by=created_by,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def list_versions(
        self, user_id: uuid.UUID, resume_id: uuid.UUID
    ) -> list[ResumeVersion]:
        rows = (await self.session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == resume_id, ResumeVersion.user_id == user_id)
            .order_by(ResumeVersion.created_at.desc())
        )).scalars().all()
        return list(rows)

    async def get_version(
        self, user_id: uuid.UUID, version_id: uuid.UUID
    ) -> ResumeVersion:
        version = (await self.session.execute(
            select(ResumeVersion).where(
                ResumeVersion.id == version_id, ResumeVersion.user_id == user_id
            )
        )).scalar_one_or_none()
        if version is None:
            raise NotFoundError(detail="Resume version not found")
        return version
