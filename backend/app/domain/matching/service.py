"""``MatchService`` -- the domain orchestrator between the pure ``MatchScorer``
and the ``job_matches`` / ``match_components`` / ``skill_gaps`` tables.

It builds the two snapshots the scorer eats, owns the on-demand
``get_or_create`` -> ``enqueue("score_match")`` lifecycle, persists a finished
``ScoreResult`` (worker callback), and answers the read queries Discovery and
the ``/matches`` API need. The scorer itself stays pure: this module never
re-implements ``score`` / ``inputs_hash`` / ``derive_gaps``.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import case, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.core.logging import current_request_id
from app.core.queue import enqueue
from app.domain.matching.gaps import _SEVERITY_ORDER, GapDraft
from app.domain.matching.scorer import JobSnapshot, ProfileSnapshot, ScoreResult
from app.domain.matching.weights import SCORER_VERSION
from app.models.job import Job, JobChunk
from app.models.match import JobMatch, MatchComponent, SkillGap
from app.models.profile import (
    CareerProfile,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
)
from app.models.skill import ProfileSkill, Skill

# Same token shape the scorer uses (`_tokens` in scorer.py) so profile `tech`
# tokens line up with the job-label tokens the `technology`/`project` dims compare.
_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")

_EMPTY_PROFILE = ProfileSnapshot(
    skill_ids=frozenset(),
    skill_labels=(),
    tech=frozenset(),
    titles=(),
    project_tech=frozenset(),
    has_degree=False,
    fields=(),
    seniority=None,
    years_experience=0.0,
    preferred_roles=(),
    locations=(),
    work_modes=frozenset(),
    salary_min=None,
    summary_text="",
)


def _tok(values: Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for value in values:
        out.update(_TOKEN_RE.findall(value.lower()))
    return frozenset(out)


def _dec(value: float) -> decimal.Decimal:
    """Cast a scorer float onto a SQLAlchemy ``Numeric`` column without the
    binary-float noise ``Decimal(float)`` would carry in."""
    return decimal.Decimal(str(value))


# Skill-gap ordering: critical < important < nice_to_have, unknown severities
# last. Same map `derive_gaps` sorts its drafts by, lifted into SQL.
_severity_rank = case(_SEVERITY_ORDER, value=SkillGap.severity, else_=99)


class MatchService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def _audit(
        self, action: str, user_id: uuid.UUID, *,
        resource_id: uuid.UUID | None = None, meta: dict[str, Any] | None = None,
    ) -> None:
        await audit(self.session, actor_type="user", action=action, actor_user_id=user_id,
                    resource_type="match", resource_id=resource_id,
                    request_id=current_request_id(), meta=meta)

    # ------------------------------------------------------------------ #
    # snapshots
    # ------------------------------------------------------------------ #
    async def build_profile_snapshot(self, user_id: uuid.UUID) -> ProfileSnapshot:
        profile = (await self.session.execute(
            select(CareerProfile).where(CareerProfile.user_id == user_id)
        )).scalar_one_or_none()
        if profile is None:
            return _EMPTY_PROFILE

        skills = (await self.session.execute(
            select(Skill)
            .join(ProfileSkill, ProfileSkill.skill_id == Skill.id)
            .where(ProfileSkill.user_id == user_id)
            .order_by(Skill.category, Skill.label)
        )).scalars().all()
        experiences = (await self.session.execute(
            select(ProfileExperience)
            .where(ProfileExperience.profile_id == profile.id)
            .order_by(ProfileExperience.order_index, ProfileExperience.id)
        )).scalars().all()
        projects = (await self.session.execute(
            select(ProfileProject)
            .where(ProfileProject.profile_id == profile.id)
            .order_by(ProfileProject.order_index, ProfileProject.id)
        )).scalars().all()
        education = (await self.session.execute(
            select(ProfileEducation)
            .where(ProfileEducation.profile_id == profile.id)
            .order_by(ProfileEducation.order_index, ProfileEducation.id)
        )).scalars().all()

        skill_labels = tuple(s.label for s in skills)
        titles = tuple(e.title.lower() for e in experiences)
        project_names = [p.name for p in projects]
        project_tech = _tok(t for p in projects for t in p.tech)
        preferred_roles = tuple(r.lower() for r in profile.preferred_roles)

        locations: list[str] = list(profile.preferred_locations)
        if profile.location:
            locations.insert(0, profile.location)

        summary_parts = [*preferred_roles, *skill_labels[:30], *titles, *project_names]
        summary_text = " • ".join(summary_parts)[:2000]

        return ProfileSnapshot(
            skill_ids=frozenset(str(s.id) for s in skills),
            skill_labels=skill_labels,
            tech=_tok(t for e in experiences for t in e.tech) | project_tech,
            titles=titles,
            project_tech=project_tech,
            has_degree=any(bool(e.degree) for e in education),
            fields=tuple(e.field.lower() for e in education if e.field),
            seniority=profile.seniority,
            years_experience=(
                float(profile.years_experience)
                if profile.years_experience is not None
                else None
            ),
            preferred_roles=preferred_roles,
            locations=tuple(x.lower() for x in locations),
            work_modes=frozenset(profile.work_modes),
            salary_min=profile.expected_salary_min,
            summary_text=summary_text,
        )

    async def build_job_snapshot(self, job_id: uuid.UUID) -> JobSnapshot:
        job = await self.session.get(Job, job_id)
        if job is None:
            raise NotFoundError(detail="Job not found")

        required = tuple(
            (str(s["skill_id"]), float(s["weight"])) for s in job.required_skills
        )
        preferred = tuple(
            (str(s["skill_id"]), float(s["weight"])) for s in job.preferred_skills
        )
        skill_labels = tuple(
            str(s["label"]).lower()
            for s in (*job.required_skills, *job.preferred_skills)
            if s.get("label")
        )
        vectors = (await self.session.execute(
            select(JobChunk.embedding)
            .where(JobChunk.job_id == job_id)
            .order_by(JobChunk.chunk_index)
        )).scalars().all()
        chunk_embeddings = tuple(
            tuple(float(x) for x in vec) for vec in vectors if vec is not None
        )

        return JobSnapshot(
            required=required,
            preferred=preferred,
            skill_labels=skill_labels,
            title=(job.title or "").lower(),
            seniority=job.seniority,
            exp_min=job.experience_min_years,
            exp_max=job.experience_max_years,
            location=job.location.lower() if job.location else None,
            work_mode=job.work_mode,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            chunk_embeddings=chunk_embeddings,
        )

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    async def _visible_ready_job_id(self, user_id: uuid.UUID, job_id: uuid.UUID) -> uuid.UUID:
        found = (await self.session.execute(
            select(Job.id).where(
                Job.id == job_id,
                or_(Job.user_id == user_id, Job.user_id.is_(None)),
                Job.deleted_at.is_(None),
                Job.status == "ready",
            )
        )).scalar_one_or_none()
        if found is None:
            raise NotFoundError(detail="Job not found")
        return found

    async def _enqueue_score(self, job_match_id: uuid.UUID) -> None:
        await enqueue(
            "score_match", str(job_match_id),
            _defer_by=2.0, _job_id=f"score_match:{job_match_id}",
        )

    async def get_or_create(self, user_id: uuid.UUID, job_id: uuid.UUID) -> JobMatch:
        # Validate the job first (visibility + state scoped) so a bad/hidden
        # job_id is a clean 404 rather than a downstream FK IntegrityError.
        await self._visible_ready_job_id(user_id, job_id)

        existing = (await self.session.execute(
            select(JobMatch).where(
                JobMatch.user_id == user_id,
                JobMatch.job_id == job_id,
                JobMatch.scorer_version == SCORER_VERSION,
                JobMatch.resume_version_id.is_(None),
            )
        )).scalar_one_or_none()
        if existing is not None:
            if existing.status == "ready":
                return existing
            # "scoring" / "failed" -> re-enqueue; _job_id dedups a live run.
            # Flip a stale "failed" back to "scoring" so the row reads honestly
            # (and the FE keeps polling) while the re-score is queued.
            if existing.status == "failed":
                existing.status = "scoring"
                existing.error = None
                await self.session.flush()
            await self._enqueue_score(existing.id)
            return existing

        match = JobMatch(
            user_id=user_id, job_id=job_id,
            scorer_version=SCORER_VERSION, status="scoring",
        )
        self.session.add(match)
        await self.session.flush()
        await self._enqueue_score(match.id)
        await self._audit("match.request", user_id, resource_id=match.id)
        return match

    async def apply_score(
        self, job_match_id: uuid.UUID, *,
        result: ScoreResult, gaps: list[GapDraft],
        explanation: str | None, explanation_meta: dict[str, Any],
        rationales: dict[str, str],
    ) -> None:
        match = await self.session.get(JobMatch, job_match_id)
        if match is None:
            raise NotFoundError(detail="Match not found")

        match.score = _dec(result.score)
        match.band = result.band
        match.dimension_scores = dict(result.dimension_scores)
        match.strengths = list(result.strengths)
        match.gaps = list(result.gaps)
        match.explanation = explanation
        match.explanation_meta = explanation_meta
        match.inputs_hash = result.inputs_hash
        match.status = "ready"
        match.error = None
        match.computed_at = dt.datetime.now(dt.UTC)

        await self.session.execute(
            delete(MatchComponent).where(MatchComponent.job_match_id == match.id)
        )
        for component in result.components:
            self.session.add(MatchComponent(
                job_match_id=match.id,
                dimension=component.dimension,
                raw_score=_dec(component.raw_score),
                weight=_dec(component.weight),
                contribution=_dec(component.contribution),
                detail=dict(component.detail),
                evidence=list(component.evidence),
            ))

        await self.session.execute(
            delete(SkillGap).where(SkillGap.job_match_id == match.id)
        )
        for draft in gaps:
            self.session.add(SkillGap(
                user_id=match.user_id,
                scope="job",
                job_match_id=match.id,
                skill_id=uuid.UUID(draft.skill_id),
                skill_slug=draft.slug,
                skill_label=draft.label,
                severity=draft.severity,
                rationale=rationales.get(draft.label),
            ))
        await self.session.flush()

    async def mark_failed(self, job_match_id: uuid.UUID, error: str) -> None:
        match = await self.session.get(JobMatch, job_match_id)
        if match is None:
            raise NotFoundError(detail="Match not found")
        match.status = "failed"
        match.error = error[:500]
        await self.session.flush()

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #
    async def get(self, user_id: uuid.UUID, match_id: uuid.UUID) -> JobMatch:
        match = (await self.session.execute(
            select(JobMatch).where(JobMatch.id == match_id, JobMatch.user_id == user_id)
        )).scalar_one_or_none()
        if match is None:
            raise NotFoundError(detail="Match not found")
        return match

    async def list_for_user(
        self, user_id: uuid.UUID, *,
        job_id: uuid.UUID | None, min_score: float | None, sort: str,
    ) -> list[JobMatch]:
        stmt = select(JobMatch).where(
            JobMatch.user_id == user_id,
            JobMatch.resume_version_id.is_(None),
        )
        if job_id is not None:
            stmt = stmt.where(JobMatch.job_id == job_id)
        if min_score is not None:
            stmt = stmt.where(JobMatch.score >= min_score)
        if sort == "recent":
            stmt = stmt.order_by(JobMatch.computed_at.desc())
        else:
            stmt = stmt.order_by(JobMatch.score.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def components(
        self, user_id: uuid.UUID, match_id: uuid.UUID
    ) -> list[MatchComponent]:
        await self.get(user_id, match_id)
        rows = (await self.session.execute(
            select(MatchComponent)
            .where(MatchComponent.job_match_id == match_id)
            .order_by(MatchComponent.contribution.desc())
        )).scalars().all()
        return list(rows)

    async def list_skill_gaps(
        self, user_id: uuid.UUID, *, scope: str, job_match_id: uuid.UUID | None
    ) -> list[SkillGap]:
        stmt = select(SkillGap).where(
            SkillGap.user_id == user_id,
            SkillGap.scope == scope,
        )
        if job_match_id is not None:
            stmt = stmt.where(SkillGap.job_match_id == job_match_id)
        stmt = stmt.order_by(_severity_rank, SkillGap.skill_label)
        return list((await self.session.execute(stmt)).scalars().all())

    async def set_gap_status(
        self, user_id: uuid.UUID, gap_id: uuid.UUID, status: str
    ) -> SkillGap:
        gap = (await self.session.execute(
            select(SkillGap).where(SkillGap.id == gap_id, SkillGap.user_id == user_id)
        )).scalar_one_or_none()
        if gap is None:
            raise NotFoundError(detail="Skill gap not found")
        gap.status = status
        await self.session.flush()
        return gap

    async def recompute(
        self, user_id: uuid.UUID, *, scope: str, job_id: uuid.UUID | None
    ) -> int:
        if scope == "all":
            job_ids = list((await self.session.execute(
                select(Job.id).where(
                    or_(Job.user_id == user_id, Job.user_id.is_(None)),
                    Job.deleted_at.is_(None),
                    Job.status == "ready",
                )
            )).scalars().all())
        else:
            if job_id is None:
                raise NotFoundError(detail="Job not found")
            job_ids = [job_id]

        for jid in job_ids:
            match = await self.get_or_create(user_id, jid)
            if match.status == "ready":
                match.status = "scoring"
            await self._enqueue_score(match.id)
        await self.session.flush()

        count = len(job_ids)
        await self._audit(
            "match.recompute", user_id, meta={"scope": scope, "count": count}
        )
        return count

    async def job_scores_for(
        self, user_id: uuid.UUID, job_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[float | None, str | None, str]]:
        if not job_ids:
            return {}
        rows = (await self.session.execute(
            select(JobMatch.job_id, JobMatch.score, JobMatch.band, JobMatch.status).where(
                JobMatch.user_id == user_id,
                JobMatch.resume_version_id.is_(None),
                JobMatch.scorer_version == SCORER_VERSION,
                JobMatch.job_id.in_(job_ids),
            )
        )).all()
        out: dict[uuid.UUID, tuple[float | None, str | None, str]] = {}
        for row in rows:
            out[row.job_id] = (
                float(row.score) if row.score else None, row.band, row.status
            )
        return out
