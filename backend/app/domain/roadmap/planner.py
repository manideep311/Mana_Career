from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.embeddings.provider import EmbeddingsProvider
from app.domain.llm.provider import LLMMessage, LLMProvider
from app.models.learning import LearningRecommendation, LearningResource, RoadmapMilestone
from app.models.match import SkillGap

log = get_logger("roadmap.planner")

_MAX_MILESTONES = 6
_SEV_RANK = {"critical": 0, "important": 1, "nice_to_have": 2}
Publish = Callable[[dict[str, Any]], Awaitable[None]]


class MilestoneDraft(BaseModel):
    # Loose bounds so the FakeLLMProvider's schema-stub (empty str / 0) validates.
    # `_draft` enforces "is this real content?" in Python and clamps est_hours.
    why_it_matters: str = Field(default="", max_length=600)
    est_hours: int = Field(default=8, ge=0, le=400)
    practice_project: str = Field(default="", max_length=400)
    checkpoint: str = Field(default="", max_length=400)


def _milestone_payload(m: RoadmapMilestone) -> dict[str, Any]:
    return {
        "id": str(m.id), "order_index": m.order_index, "skill_slug": m.skill_slug,
        "skill_label": m.skill_label, "title": m.title, "why_it_matters": m.why_it_matters,
        "resource_ids": [str(r) for r in m.resource_ids], "est_hours": m.est_hours,
        "practice_project": m.practice_project, "checkpoint": m.checkpoint,
        "status": m.status,
    }


class RoadmapPlanner:
    def __init__(
        self, session: AsyncSession, *, llm: LLMProvider, embeddings: EmbeddingsProvider
    ) -> None:
        self._session = session
        self._llm = llm
        self._embeddings = embeddings

    async def plan(
        self,
        user_id: uuid.UUID,
        *,
        scope: str,
        job_id: uuid.UUID | None,
        constraints: dict[str, Any],
        publish: Publish,
    ) -> uuid.UUID:
        rec = (
            await self._session.execute(
                select(LearningRecommendation).where(
                    LearningRecommendation.user_id == user_id,
                    LearningRecommendation.status == "planning",
                ).order_by(LearningRecommendation.created_at.desc())
            )
        ).scalars().first()
        if rec is None:
            raise ValueError("no planning recommendation for user")

        try:
            gaps = await self._top_gaps(user_id)
            n = 0
            for gap in gaps:
                resources = await self._retrieve(gap)
                draft = await self._draft(gap, resources, constraints)
                if draft is None:
                    continue
                ms = RoadmapMilestone(
                    recommendation_id=rec.id, user_id=user_id, order_index=n,
                    skill_id=gap.skill_id, skill_slug=gap.skill_slug,
                    skill_label=gap.skill_label,
                    title=f"Close your {gap.skill_label} gap",
                    why_it_matters=draft.why_it_matters,
                    resource_ids=[r.id for r in resources],
                    est_hours=draft.est_hours, practice_project=draft.practice_project,
                    checkpoint=draft.checkpoint, status="not_started",
                )
                self._session.add(ms)
                await self._session.flush()
                n += 1
                await publish({"event": "milestone", "milestone": _milestone_payload(ms)})

            rec.status = "active"
            rec.summary = f"{n} milestones to close your top skill gaps."
            first = (
                await self._session.execute(
                    select(RoadmapMilestone)
                    .where(RoadmapMilestone.recommendation_id == rec.id)
                    .order_by(RoadmapMilestone.order_index)
                )
            ).scalars().first()
            rec.next_step = first.title if first is not None else None
            await self._session.flush()
            await publish({"event": "done", "status": "active", "id": str(rec.id)})
            return rec.id
        except Exception as e:  # surface as an archived roadmap + SSE error
            log.exception("roadmap_plan_failed", rec_id=str(rec.id))
            rec.status = "archived"
            rec.generation_meta = {**rec.generation_meta, "error": str(e)}
            await self._session.flush()
            # `status: "archived"` so status_stream's terminal check fires for the relay.
            await publish(
                {"event": "error", "status": "archived",
                 "message": "We couldn't build your roadmap."}
            )
            raise

    async def _top_gaps(self, user_id: uuid.UUID) -> list[SkillGap]:
        rows = (
            await self._session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == user_id, SkillGap.scope == "aggregate",
                    SkillGap.status == "open",
                )
            )
        ).scalars().all()
        rows_sorted = sorted(
            rows, key=lambda g: (_SEV_RANK.get(g.severity, 9), -g.frequency)
        )
        return rows_sorted[:_MAX_MILESTONES]

    async def _retrieve(self, gap: SkillGap) -> list[LearningResource]:
        q = await self._embeddings.embed_query(f"Learn {gap.skill_label}")
        rows = (
            await self._session.execute(
                select(LearningResource)
                .where(LearningResource.is_active.is_(True))
                .order_by(LearningResource.embedding.cosine_distance(q))
                .limit(8)
            )
        ).scalars().all()
        overlap = [r for r in rows if gap.skill_slug in (r.skills or [])]
        picked = (overlap or list(rows))[:3]
        return picked

    async def _draft(
        self, gap: SkillGap, resources: list[LearningResource], constraints: dict[str, Any]
    ) -> MilestoneDraft | None:
        if not resources:
            return None
        catalog = "\n".join(
            f"- [{r.id}] {r.title} ({r.provider}, {r.type}, {r.level}) — {r.summary} {r.url}"
            for r in resources
        )
        sys = (
            "You are a pragmatic engineering mentor. Given a skill gap and a short "
            "list of vetted learning resources, produce ONE milestone. Recommend ONLY "
            "from the provided resources. Return strict JSON matching the schema."
        )
        usr = (
            f"Skill gap: {gap.skill_label} (severity {gap.severity}, appears in "
            f"{gap.frequency} of the user's job matches).\n"
            f"Constraints: {constraints or 'none'}.\n\n"
            f"Resources:\n{catalog}\n\n"
            "Write why_it_matters (2-3 sentences, concrete), est_hours (integer), "
            "practice_project (a small buildable thing), checkpoint (how they'll know "
            "they've got it)."
        )
        messages: list[LLMMessage] = [
            {"role": "system", "content": sys},
            {"role": "user", "content": usr},
        ]
        try:
            result = await self._llm.complete(messages, schema=MilestoneDraft, max_tokens=700)
        except Exception:  # one bad milestone must not sink the whole roadmap
            log.warning("roadmap_draft_llm_failed", skill=gap.skill_slug)
            return None
        if result.structured is None:
            return None
        try:
            draft = MilestoneDraft.model_validate(result.structured)
        except Exception:  # malformed structured payload -> drop this milestone
            return None
        # "Is this real content?" — the FakeLLMProvider returns empty strings.
        if not draft.why_it_matters.strip() or not draft.practice_project.strip():
            return None
        draft = draft.model_copy(update={"est_hours": max(1, min(draft.est_hours, 200))})
        return draft
