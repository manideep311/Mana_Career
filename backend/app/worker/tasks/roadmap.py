from __future__ import annotations

import json
import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.events import roadmap_channel
from app.core.logging import get_logger
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.llm.factory import get_llm_provider
from app.domain.roadmap.planner import RoadmapPlanner
from app.models.learning import LearningRecommendation

__all__ = ["plan_roadmap"]

log = get_logger("worker.roadmap")


async def plan_roadmap(ctx: dict[str, Any], rec_id: str) -> None:
    # Mirrors app/worker/tasks/agent.py::_run_or_resume -- own Redis conn +
    # aclose() in finally; ARQ's ctx does NOT carry a redis pool in this repo.
    log.info("plan_roadmap_start", rec_id=rec_id, job_id=ctx.get("job_id"))
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    channel = roadmap_channel(rec_id)

    async def publish(frame: dict[str, Any]) -> None:
        await redis.publish(channel, json.dumps(frame, default=str))

    try:
        async with AsyncSessionLocal() as session:
            rec = (
                await session.execute(
                    select(LearningRecommendation).where(
                        LearningRecommendation.id == uuid.UUID(rec_id)
                    )
                )
            ).scalar_one_or_none()
            if rec is None or rec.status != "planning":
                log.info(
                    "plan_roadmap_skipped",
                    rec_id=rec_id,
                    reason="missing" if rec is None else rec.status,
                )
                return
            planner = RoadmapPlanner(
                session,
                llm=get_llm_provider(settings),
                embeddings=get_embeddings_provider(settings),
            )
            try:
                await planner.plan(
                    rec.user_id,
                    scope=rec.scope,
                    job_id=rec.job_id,
                    constraints=dict(rec.constraints),
                    publish=publish,
                )
            finally:
                # planner.plan() sets status active/archived on its own session;
                # commit either outcome so the row + milestones persist.
                await session.commit()
    finally:
        await redis.aclose()
