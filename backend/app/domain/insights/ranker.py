from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.job import Job
from app.models.learning import LearningRecommendation, RoadmapMilestone
from app.models.match import JobMatch, SkillGap


@dataclass(frozen=True)
class NextStepData:
    kind: str
    title: str
    reason: str
    entity_type: str | None
    entity_id: uuid.UUID | None


async def next_best_action(
    session: AsyncSession, user_id: uuid.UUID
) -> NextStepData | None:
    # (a) an application waiting on human approval
    row = (
        await session.execute(
            select(Application.id).where(
                Application.user_id == user_id,
                Application.status == "awaiting_approval",
                Application.deleted_at.is_(None),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return NextStepData(
            kind="review_approval",
            title="Review an application that's ready to send",
            reason="An application is waiting for your approval before it goes out.",
            entity_type="application", entity_id=row,
        )

    # (b) scored jobs but no aggregate gap rollup yet
    match_count = (
        await session.execute(
            select(func.count()).select_from(JobMatch).where(JobMatch.user_id == user_id)
        )
    ).scalar_one()
    agg_count = (
        await session.execute(
            select(func.count()).select_from(SkillGap).where(
                SkillGap.user_id == user_id, SkillGap.scope == "aggregate"
            )
        )
    ).scalar_one()
    if match_count > 0 and agg_count == 0:
        return NextStepData(
            kind="refresh_gaps", title="Refresh your skill-gap analysis",
            reason="You've scored some jobs -- roll up the gaps to see what to learn.",
            entity_type=None, entity_id=None,
        )

    # (c) an active roadmap with a milestone not yet started
    ms = (
        await session.execute(
            select(RoadmapMilestone.recommendation_id, RoadmapMilestone.title)
            .join(
                LearningRecommendation,
                LearningRecommendation.id == RoadmapMilestone.recommendation_id,
            )
            .where(
                RoadmapMilestone.user_id == user_id,
                RoadmapMilestone.status == "not_started",
                LearningRecommendation.status == "active",
            )
            .order_by(RoadmapMilestone.order_index)
            .limit(1)
        )
    ).first()
    if ms is not None:
        return NextStepData(
            kind="start_milestone", title="Start your next learning milestone",
            reason=f"'{ms.title}' is ready to begin.",
            entity_type="roadmap", entity_id=ms.recommendation_id,
        )

    # (d) fewer than 3 jobs tracked
    own_jobs = (
        await session.execute(
            select(func.count()).select_from(Job).where(
                Job.user_id == user_id, Job.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    if own_jobs < 3:
        return NextStepData(
            kind="add_job", title="Add a job you're interested in",
            reason="Track a few roles so Mana can tailor its guidance.",
            entity_type=None, entity_id=None,
        )

    # (e) a stale application still sitting at 'applied'
    stale_cutoff = datetime.now(UTC) - timedelta(days=14)
    stale = (
        await session.execute(
            select(Application.id).where(
                Application.user_id == user_id,
                Application.status == "applied",
                Application.deleted_at.is_(None),
                Application.last_status_change_at < stale_cutoff,
            ).order_by(Application.last_status_change_at).limit(1)
        )
    ).scalar_one_or_none()
    if stale is not None:
        return NextStepData(
            kind="follow_up", title="Follow up on a stale application",
            reason="It's been over two weeks since you applied -- a nudge can help.",
            entity_type="application", entity_id=stale,
        )

    return None
