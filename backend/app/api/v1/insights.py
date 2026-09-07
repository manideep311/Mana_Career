from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.insights import (
    InsightsOut,
    NextStep,
    RoadmapSummary,
    SkillMention,
)
from app.api.v1.schemas.skill_gaps import SkillGapOut
from app.domain.insights.ranker import next_best_action
from app.domain.insights.service import InsightsService
from app.domain.matching.service import MatchService
from app.models.match import JobMatch, SkillGap

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("")
async def get_insights(db: DbDep, user: CurrentUser) -> InsightsOut:
    # Lazy aggregate rollup: the first Insights view after scoring has no
    # aggregate rows yet. app.api may import both services.
    agg_count = (
        await db.execute(
            select(func.count()).select_from(SkillGap).where(
                SkillGap.user_id == user.id, SkillGap.scope == "aggregate"
            )
        )
    ).scalar_one()
    match_count = (
        await db.execute(
            select(func.count()).select_from(JobMatch).where(
                JobMatch.user_id == user.id
            )
        )
    ).scalar_one()
    if agg_count == 0 and match_count > 0:
        await MatchService(db).aggregate_skill_gaps(user.id)

    data = await InsightsService(db).compose(user.id)
    nba = await next_best_action(db, user.id)
    return InsightsOut(
        strengths=[
            SkillMention(skill_slug=m.skill_slug, skill_label=m.skill_label, detail=m.detail)
            for m in data.strengths
        ],
        skills_to_develop=[SkillGapOut(**g) for g in data.skills_to_develop],
        recommended_next_step=(
            NextStep(
                kind=nba.kind, title=nba.title, reason=nba.reason,
                entity_type=nba.entity_type, entity_id=nba.entity_id,
            )
            if nba is not None
            else None
        ),
        trending_skills=[
            SkillMention(skill_slug=m.skill_slug, skill_label=m.skill_label, detail=m.detail)
            for m in data.trending_skills
        ],
        suggested_projects=data.suggested_projects,
        roadmap_summary=(
            RoadmapSummary(
                id=data.roadmap_summary.id, title=data.roadmap_summary.title,
                next_step=data.roadmap_summary.next_step,
                milestones_done=data.roadmap_summary.milestones_done,
                milestones_total=data.roadmap_summary.milestones_total,
            )
            if data.roadmap_summary is not None
            else None
        ),
    )
