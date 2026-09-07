from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.learning import LearningRecommendation, RoadmapMilestone
from app.models.match import JobMatch, SkillGap

_SEV_RANK = {"critical": 0, "important": 1, "nice_to_have": 2}


@dataclass(frozen=True)
class MentionData:
    skill_slug: str
    skill_label: str
    detail: str | None


@dataclass(frozen=True)
class RoadmapSummaryData:
    id: uuid.UUID
    title: str
    next_step: str | None
    milestones_done: int
    milestones_total: int


@dataclass
class InsightsData:
    strengths: list[MentionData] = field(default_factory=list)
    skills_to_develop: list[dict[str, Any]] = field(default_factory=list)
    trending_skills: list[MentionData] = field(default_factory=list)
    suggested_projects: list[str] = field(default_factory=list)
    roadmap_summary: RoadmapSummaryData | None = None


def _gap_dict(g: SkillGap) -> dict[str, Any]:
    return {
        "id": g.id, "scope": g.scope, "job_match_id": g.job_match_id,
        "skill_slug": g.skill_slug, "skill_label": g.skill_label,
        "severity": g.severity, "frequency": g.frequency,
        "rationale": g.rationale, "status": g.status,
    }


class InsightsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compose(self, user_id: uuid.UUID) -> InsightsData:
        return InsightsData(
            strengths=await self._strengths(user_id),
            skills_to_develop=await self._skills_to_develop(user_id),
            trending_skills=await self._trending(),
            suggested_projects=await self._suggested_projects(user_id),
            roadmap_summary=await self._roadmap_summary(user_id),
        )

    async def _strengths(self, user_id: uuid.UUID) -> list[MentionData]:
        rows = (
            await self._session.execute(
                select(JobMatch.strengths)
                .where(JobMatch.user_id == user_id, JobMatch.status == "ready")
                .order_by(JobMatch.computed_at.desc())
                .limit(20)
            )
        ).scalars().all()
        counter: Counter[str] = Counter()
        for strengths in rows:
            for s in strengths or []:
                dim = str(s.get("dimension") or "").strip()
                if dim:
                    counter[dim] += 1
        out: list[MentionData] = []
        for dim, n in counter.most_common(6):
            out.append(
                MentionData(
                    skill_slug=dim, skill_label=dim.replace("_", " ").title(),
                    detail=f"Strong across {n} of your recent matches",
                )
            )
        return out

    async def _skills_to_develop(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == user_id, SkillGap.scope == "aggregate"
                )
            )
        ).scalars().all()
        ranked = sorted(
            rows, key=lambda g: (_SEV_RANK.get(g.severity, 9), -g.frequency)
        )
        return [_gap_dict(g) for g in ranked[:8]]

    async def _trending(self) -> list[MentionData]:
        rows = (
            await self._session.execute(
                select(Job.required_skills).where(
                    Job.status == "ready", Job.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        label: dict[str, str] = {}
        counter: Counter[str] = Counter()
        for req in rows:
            for sk in req or []:
                slug = str(sk.get("slug") or "").strip()
                if not slug:
                    continue
                counter[slug] += 1
                label.setdefault(slug, str(sk.get("label") or slug))
        return [
            MentionData(
                skill_slug=slug, skill_label=label.get(slug, slug),
                detail=f"in {n} roles",
            )
            for slug, n in counter.most_common(10)
        ]

    async def _active_recommendation(
        self, user_id: uuid.UUID
    ) -> LearningRecommendation | None:
        return (
            await self._session.execute(
                select(LearningRecommendation)
                .where(
                    LearningRecommendation.user_id == user_id,
                    LearningRecommendation.status == "active",
                )
                .order_by(LearningRecommendation.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

    async def _suggested_projects(self, user_id: uuid.UUID) -> list[str]:
        rec = await self._active_recommendation(user_id)
        if rec is None:
            return []
        rows = (
            await self._session.execute(
                select(RoadmapMilestone.practice_project)
                .where(
                    RoadmapMilestone.recommendation_id == rec.id,
                    RoadmapMilestone.status.in_(("not_started", "in_progress")),
                    RoadmapMilestone.practice_project.is_not(None),
                )
                .order_by(RoadmapMilestone.order_index)
                .limit(4)
            )
        ).scalars().all()
        return [p for p in rows if p]

    async def _roadmap_summary(
        self, user_id: uuid.UUID
    ) -> RoadmapSummaryData | None:
        rec = await self._active_recommendation(user_id)
        if rec is None:
            return None
        total = (
            await self._session.execute(
                select(func.count()).select_from(RoadmapMilestone).where(
                    RoadmapMilestone.recommendation_id == rec.id
                )
            )
        ).scalar_one()
        done = (
            await self._session.execute(
                select(func.count()).select_from(RoadmapMilestone).where(
                    RoadmapMilestone.recommendation_id == rec.id,
                    RoadmapMilestone.status == "done",
                )
            )
        ).scalar_one()
        return RoadmapSummaryData(
            id=rec.id, title=rec.title, next_step=rec.next_step,
            milestones_done=int(done), milestones_total=int(total),
        )
