"""InsightsService.compose -- DB integration, CI-deferred."""
from __future__ import annotations

from datetime import UTC, datetime

from app.domain.insights.service import InsightsService
from app.models.job import Job
from app.models.learning import LearningRecommendation, RoadmapMilestone
from app.models.match import JobMatch, SkillGap
from app.models.skill import Skill
from app.models.user import User


async def _seed(db_session, email):
    user = User(email=email, password_hash="x", full_name="U")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id, is_seed=False, source="user_paste", status="ready",
        raw_text="x" * 60, title="Backend Engineer", company="Acme",
        required_skills=[], preferred_skills=[],
    )
    db_session.add(job)
    await db_session.flush()

    match = JobMatch(
        user_id=user.id, job_id=job.id, scorer_version="v1", status="ready",
        strengths=[{"dimension": "experience", "raw_score": 0.8, "contribution": 20.0}],
        computed_at=datetime.now(UTC),
    )
    db_session.add(match)
    await db_session.flush()

    skill_a = Skill(slug="python", label="Python", category="language", aliases=[])
    skill_b = Skill(slug="sql", label="SQL", category="language", aliases=[])
    db_session.add_all([skill_a, skill_b])
    await db_session.flush()

    db_session.add_all([
        SkillGap(
            user_id=user.id, scope="aggregate", skill_id=skill_a.id,
            skill_slug="python", skill_label="Python", severity="critical",
            frequency=3, status="open",
        ),
        SkillGap(
            user_id=user.id, scope="aggregate", skill_id=skill_b.id,
            skill_slug="sql", skill_label="SQL", severity="important",
            frequency=1, status="open",
        ),
    ])

    rec = LearningRecommendation(
        user_id=user.id, scope="aggregate", title="Close your top skill gaps",
        constraints={}, status="active", generation_meta={},
    )
    db_session.add(rec)
    await db_session.flush()

    db_session.add_all([
        RoadmapMilestone(
            recommendation_id=rec.id, user_id=user.id, order_index=0,
            skill_slug="python", skill_label="Python", title="Ship a CLI in Python",
            why_it_matters="It is the top gap.", status="not_started",
            practice_project="Build a small CLI tool",
        ),
        RoadmapMilestone(
            recommendation_id=rec.id, user_id=user.id, order_index=1,
            skill_slug="sql", skill_label="SQL", title="Model a schema",
            why_it_matters="Every backend touches a database.", status="done",
        ),
    ])
    await db_session.flush()
    return user


async def test_compose_rolls_up_strengths_gaps_and_roadmap(db_session):
    user = await _seed(db_session, "insights-svc@x.com")

    out = await InsightsService(db_session).compose(user.id)

    assert any(
        m.skill_slug == "experience" and m.skill_label == "Experience"
        for m in out.strengths
    )

    assert len(out.skills_to_develop) <= 8
    assert len(out.skills_to_develop) == 2
    # critical sorts ahead of important
    assert out.skills_to_develop[0]["skill_slug"] == "python"

    assert "Build a small CLI tool" in out.suggested_projects

    assert out.roadmap_summary is not None
    assert out.roadmap_summary.milestones_total == 2
    assert out.roadmap_summary.milestones_done == 1
