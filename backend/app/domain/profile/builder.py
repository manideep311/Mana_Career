from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.embeddings.provider import EmbeddingsProvider
from app.domain.profile.service import ProfileService
from app.domain.skills.normalizer import SkillMatch, SkillNormalizer
from app.models.profile import ProfileExperience, ProfileProject
from app.models.resume import Resume
from app.models.skill import ProfileSkill

_RESUME_SOURCE = "resume_extraction"


@dataclass(frozen=True)
class BuildResult:
    matched: int
    evidence_total: int
    unmatched: list[str]


def _clean_strings(values: Iterable[Any]) -> list[str]:
    """Keep only the non-blank string entries of a free-text list column."""
    return [v for v in values if isinstance(v, str) and v.strip()]


class ProfileBuilder:
    """Map the free-text skills scattered across a profile onto the taxonomy.

    Deterministic pass run from the ``build_profile`` ARQ task after
    ``confirm_profile``. It reads the ``tech[]`` arrays on the profile's
    experiences and projects plus the primary résumé's extracted ``skills[]``,
    normalises every string through :class:`SkillNormalizer`, and rewrites the
    ``source="resume_extraction"`` rows of ``profile_skills`` so each carries
    ``evidence_refs`` pointing back at the rows that mentioned the skill.

    ``source="user"`` rows are authoritative: they are never deleted, and a
    skill that already has a user row is skipped by the insert loop (the
    ``(profile_id, skill_id)`` unique constraint would otherwise be violated).
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        embeddings: EmbeddingsProvider | None = None,
    ) -> None:
        self.session = session
        self.embeddings = embeddings

    async def rebuild(self, user_id: uuid.UUID) -> BuildResult:
        profile = await ProfileService(self.session).get_or_create(user_id)

        # (raw, kind, ref_id) for every free-text skill string on the profile.
        collected: list[tuple[str, str, uuid.UUID]] = []

        exp_rows = (
            await self.session.execute(
                select(ProfileExperience)
                .where(
                    ProfileExperience.profile_id == profile.id,
                    ProfileExperience.source == _RESUME_SOURCE,
                )
                .order_by(ProfileExperience.order_index, ProfileExperience.id)
            )
        ).scalars().all()
        for exp in exp_rows:
            for raw in _clean_strings(exp.tech):
                collected.append((raw, "experience", exp.id))

        proj_rows = (
            await self.session.execute(
                select(ProfileProject)
                .where(
                    ProfileProject.profile_id == profile.id,
                    ProfileProject.source == _RESUME_SOURCE,
                )
                .order_by(ProfileProject.order_index, ProfileProject.id)
            )
        ).scalars().all()
        for proj in proj_rows:
            for raw in _clean_strings(proj.tech):
                collected.append((raw, "project", proj.id))

        resume = (
            await self.session.execute(
                select(Resume).where(
                    Resume.user_id == user_id,
                    Resume.is_primary.is_(True),
                    Resume.deleted_at.is_(None),
                    Resume.status == "extracted",
                    Resume.extraction.is_not(None),
                )
            )
        ).scalar_one_or_none()
        if resume is not None and resume.extraction is not None:
            raw_skills = resume.extraction.get("skills", [])
            if isinstance(raw_skills, list):
                for raw in _clean_strings(raw_skills):
                    collected.append((raw, "resume", resume.id))

        normalizer = SkillNormalizer(
            self.session,
            self.embeddings or get_embeddings_provider(get_settings()),
        )
        await normalizer.load()

        # Normalise each distinct raw (case-insensitive) exactly once.
        matched_by_key: dict[str, SkillMatch | None] = {}
        for raw, _kind, _ref_id in collected:
            key = raw.casefold()
            if key not in matched_by_key:
                matched_by_key[key] = await normalizer.normalize(raw)

        # Group evidence by resolved skill; keep the raws that resolved to nothing.
        evidence_by_skill: dict[uuid.UUID, list[dict[str, Any]]] = {}
        unmatched_by_key: dict[str, str] = {}
        for raw, kind, ref_id in collected:
            match = matched_by_key[raw.casefold()]
            if match is None:
                unmatched_by_key.setdefault(raw.casefold(), raw)
                continue
            entry: dict[str, Any] = {
                "kind": kind,
                "ref_id": str(ref_id),
                "raw": raw,
            }
            refs = evidence_by_skill.setdefault(match.skill_id, [])
            if entry not in refs:
                refs.append(entry)

        # Rewrite only the resume-extraction rows; user rows stay put.
        await self.session.execute(
            delete(ProfileSkill).where(
                ProfileSkill.profile_id == profile.id,
                ProfileSkill.source == _RESUME_SOURCE,
            )
        )
        surviving_skill_ids = set(
            (
                await self.session.execute(
                    select(ProfileSkill.skill_id).where(
                        ProfileSkill.profile_id == profile.id
                    )
                )
            ).scalars().all()
        )

        matched = 0
        for skill_id, refs in evidence_by_skill.items():
            if skill_id in surviving_skill_ids:
                continue
            self.session.add(
                ProfileSkill(
                    user_id=user_id,
                    profile_id=profile.id,
                    skill_id=skill_id,
                    source=_RESUME_SOURCE,
                    evidence_refs=refs,
                )
            )
            matched += 1

        await self.session.flush()
        await ProfileService(self.session)._recompute(profile)

        return BuildResult(
            matched=matched,
            evidence_total=sum(len(refs) for refs in evidence_by_skill.values()),
            unmatched=sorted(unmatched_by_key.values()),
        )
