from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.core.queue import enqueue
from app.models.learning import LearningRecommendation, RoadmapMilestone
from app.models.match import SkillGap

_REC_STATUS = {"active", "archived"}
_MS_STATUS = {"not_started", "in_progress", "done"}


class RoadmapService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        scope: str,
        job_id: uuid.UUID | None,
        constraints: dict[str, Any],
        title: str,
    ) -> LearningRecommendation:
        rec = LearningRecommendation(
            user_id=user_id,
            scope=scope,
            job_id=job_id,
            title=title,
            constraints=constraints,
            status="planning",
        )
        self._session.add(rec)
        await self._session.flush()
        return rec

    async def enqueue_plan(self, rec_id: uuid.UUID) -> None:
        await enqueue("plan_roadmap", str(rec_id), _job_id=f"plan_roadmap:{rec_id}")

    async def list_(self, user_id: uuid.UUID) -> list[LearningRecommendation]:
        rows = (
            await self._session.execute(
                select(LearningRecommendation)
                .where(LearningRecommendation.user_id == user_id)
                .order_by(LearningRecommendation.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def get(
        self, user_id: uuid.UUID, rec_id: uuid.UUID
    ) -> LearningRecommendation:
        rec = (
            await self._session.execute(
                select(LearningRecommendation).where(
                    LearningRecommendation.id == rec_id,
                    LearningRecommendation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if rec is None:
            raise NotFoundError(detail="Roadmap not found")
        return rec

    async def milestones(self, rec_id: uuid.UUID) -> list[RoadmapMilestone]:
        rows = (
            await self._session.execute(
                select(RoadmapMilestone)
                .where(RoadmapMilestone.recommendation_id == rec_id)
                .order_by(RoadmapMilestone.order_index)
            )
        ).scalars().all()
        return list(rows)

    async def set_status(
        self, user_id: uuid.UUID, rec_id: uuid.UUID, status: str
    ) -> LearningRecommendation:
        if status not in _REC_STATUS:
            raise ValidationAppError(f"Can't set roadmap status to {status!r}.")
        rec = await self.get(user_id, rec_id)
        rec.status = status
        await self._session.flush()
        return rec

    async def set_milestone_status(
        self,
        user_id: uuid.UUID,
        rec_id: uuid.UUID,
        milestone_id: uuid.UUID,
        status: str,
    ) -> RoadmapMilestone:
        if status not in _MS_STATUS:
            raise ValidationAppError(f"Can't set milestone status to {status!r}.")
        await self.get(user_id, rec_id)  # ownership + 404
        ms = (
            await self._session.execute(
                select(RoadmapMilestone).where(
                    RoadmapMilestone.id == milestone_id,
                    RoadmapMilestone.recommendation_id == rec_id,
                )
            )
        ).scalar_one_or_none()
        if ms is None:
            raise NotFoundError(detail="Milestone not found")

        was_done = ms.status == "done"
        ms.status = status
        if status == "done":
            ms.completed_at = datetime.now(UTC)
            await self._session.execute(
                update(SkillGap)
                .where(
                    SkillGap.user_id == user_id,
                    SkillGap.scope == "aggregate",
                    SkillGap.skill_slug == ms.skill_slug,
                )
                .values(status="closed", addressed_by_roadmap_id=rec_id)
            )
        elif was_done:
            ms.completed_at = None
            await self._session.execute(
                update(SkillGap)
                .where(
                    SkillGap.user_id == user_id,
                    SkillGap.scope == "aggregate",
                    SkillGap.skill_slug == ms.skill_slug,
                )
                .values(status="open", addressed_by_roadmap_id=None)
            )
        await self._session.flush()
        return ms
