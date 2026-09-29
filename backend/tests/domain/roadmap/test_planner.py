"""RoadmapPlanner -- DB integration, CI-deferred.

Asserts the planning->active transition and the publish frame sequence. With
``LLM_PROVIDER=fake`` every model draft comes back empty, so each milestone is
written by the deterministic template from the stored gap and catalogue, and the
roadmap still reaches ``status='active'`` with a terminal ``done`` frame.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.llm.factory import get_llm_provider
from app.domain.roadmap.planner import RoadmapPlanner
from app.models.learning import LearningRecommendation
from app.models.match import SkillGap
from app.models.skill import Skill
from app.models.user import User


async def _seed(db_session) -> tuple[User, LearningRecommendation]:
    user = User(email="roadmap-planner@x.com", password_hash="x", full_name="U")
    db_session.add(user)
    await db_session.flush()

    skill = Skill(slug="kubernetes", label="Kubernetes", category="tool", aliases=[])
    db_session.add(skill)
    await db_session.flush()

    from app.models.learning import LearningResource

    resource = LearningResource(
        title="Kubernetes the Hard Way",
        provider="Google",
        url="https://example.com/k8s-hard-way",
        type="course",
        skills=["kubernetes"],
        level="intermediate",
        cost="free",
        summary="Bootstrap a cluster by hand to learn every moving part.",
        embedding=[0.1] * 1024,
    )
    db_session.add(resource)
    await db_session.flush()

    db_session.add(
        SkillGap(
            user_id=user.id, scope="aggregate", skill_id=skill.id,
            skill_slug="kubernetes", skill_label="Kubernetes",
            severity="critical", frequency=2, status="open",
        )
    )
    rec = LearningRecommendation(
        user_id=user.id, scope="aggregate", title="Close your top skill gaps",
        constraints={}, status="planning", generation_meta={},
    )
    db_session.add(rec)
    await db_session.flush()
    return user, rec


async def test_plan_transitions_planning_to_active_and_publishes_done(db_session):
    user, rec = await _seed(db_session)
    assert rec.status == "planning"

    frames: list[dict[str, Any]] = []

    async def collect(frame: dict[str, Any]) -> None:
        frames.append(frame)

    settings = get_settings()
    planner = RoadmapPlanner(
        db_session,
        llm=get_llm_provider(settings),
        embeddings=get_embeddings_provider(settings),
    )

    rec_id = await planner.plan(
        user.id, scope="aggregate", job_id=None, constraints={}, publish=collect
    )

    assert rec_id == rec.id

    refreshed = (
        await db_session.execute(
            select(LearningRecommendation).where(LearningRecommendation.id == rec.id)
        )
    ).scalar_one()
    assert refreshed.status == "active"

    assert frames, "planner published no frames"
    assert frames[-1]["event"] == "done"
    assert frames[-1]["status"] == "active"
    assert frames[-1]["id"] == str(rec.id)

    # The fake LLM yields empty drafts, so the template writes the milestone.
    milestone_frames = [f for f in frames if f["event"] == "milestone"]
    assert len(milestone_frames) == 1
    ms = milestone_frames[0]["milestone"]
    assert ms["skill_slug"] == "kubernetes"
    assert "2 of your job matches, usually as a requirement" in ms["why_it_matters"]
    assert "Kubernetes" in ms["practice_project"]
    assert refreshed.summary == "1 milestone to close your top skill gaps."
    assert refreshed.next_step == "Close your Kubernetes gap"
    assert refreshed.generation_meta["drafted_by"] == {"model": 0, "template": 1}
