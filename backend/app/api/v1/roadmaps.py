from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.roadmaps import (
    MilestoneOut,
    MilestonePatchIn,
    RoadmapCreateIn,
    RoadmapDetailOut,
    RoadmapListOut,
    RoadmapOut,
    RoadmapPatchIn,
    RoadmapRefOut,
)
from app.domain.roadmap.service import RoadmapService
from app.models.job import Job
from app.models.learning import LearningRecommendation, RoadmapMilestone

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])


def _roadmap_out(r: LearningRecommendation) -> RoadmapOut:
    return RoadmapOut(
        id=r.id, scope=r.scope, job_id=r.job_id, title=r.title, summary=r.summary,
        next_step=r.next_step, status=r.status,
        created_at=r.created_at, updated_at=r.updated_at,
    )


def _milestone_out(m: RoadmapMilestone) -> MilestoneOut:
    return MilestoneOut(
        id=m.id, order_index=m.order_index, skill_slug=m.skill_slug,
        skill_label=m.skill_label, title=m.title, why_it_matters=m.why_it_matters,
        resource_ids=list(m.resource_ids), est_hours=m.est_hours,
        practice_project=m.practice_project, checkpoint=m.checkpoint,
        status=m.status, completed_at=m.completed_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_roadmap(
    body: RoadmapCreateIn, db: DbDep, user: CurrentUser
) -> RoadmapRefOut:
    title = "Learning roadmap"
    if body.job_id is not None:
        job = (
            await db.execute(select(Job).where(Job.id == body.job_id))
        ).scalar_one_or_none()
        if job is not None and job.title:
            title = f"Roadmap for {job.title}"
    svc = RoadmapService(db)
    rec = await svc.create(
        user.id, scope=body.scope, job_id=body.job_id,
        constraints=body.constraints, title=title,
    )
    await db.commit()
    await svc.enqueue_plan(rec.id)
    return RoadmapRefOut(id=rec.id)


@router.get("")
async def list_roadmaps(db: DbDep, user: CurrentUser) -> RoadmapListOut:
    rows = await RoadmapService(db).list_(user.id)
    return RoadmapListOut(items=[_roadmap_out(r) for r in rows])


@router.get("/{roadmap_id}")
async def get_roadmap(
    roadmap_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> RoadmapDetailOut:
    svc = RoadmapService(db)
    rec = await svc.get(user.id, roadmap_id)
    ms = await svc.milestones(roadmap_id)
    return RoadmapDetailOut(
        **_roadmap_out(rec).model_dump(),
        milestones=[_milestone_out(m) for m in ms],
    )


@router.patch("/{roadmap_id}")
async def patch_roadmap(
    roadmap_id: uuid.UUID, body: RoadmapPatchIn, db: DbDep, user: CurrentUser
) -> RoadmapOut:
    return _roadmap_out(
        await RoadmapService(db).set_status(user.id, roadmap_id, body.status)
    )


@router.patch("/{roadmap_id}/milestones/{milestone_id}")
async def patch_milestone(
    roadmap_id: uuid.UUID, milestone_id: uuid.UUID, body: MilestonePatchIn,
    db: DbDep, user: CurrentUser,
) -> MilestoneOut:
    return _milestone_out(
        await RoadmapService(db).set_milestone_status(
            user.id, roadmap_id, milestone_id, body.status
        )
    )
