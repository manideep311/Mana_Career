"""MatchService.aggregate_skill_gaps -- DB integration, CI-deferred."""
from __future__ import annotations

from sqlalchemy import func, select

from app.domain.matching.service import MatchService
from app.models.job import Job
from app.models.match import JobMatch, SkillGap
from app.models.skill import Skill
from app.models.user import User


async def _agg_count(db_session, user_id) -> int:
    return (
        await db_session.execute(
            select(func.count())
            .select_from(SkillGap)
            .where(SkillGap.scope == "aggregate", SkillGap.user_id == user_id)
        )
    ).scalar_one()


async def _seed(db_session):
    user = User(email="agg-gaps@x.com", password_hash="x", full_name="U")
    db_session.add(user)
    await db_session.flush()

    # Two distinct jobs: the partial unique index on
    # (user_id, job_id, scorer_version) WHERE resume_version_id IS NULL forbids
    # two current-profile matches against the *same* job.
    job1 = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    job2 = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="y" * 60,
        title="Platform Engineer", company="Globex", required_skills=[], preferred_skills=[],
    )
    db_session.add_all([job1, job2])
    await db_session.flush()

    skill_a = Skill(slug="kubernetes", label="Kubernetes", category="tool", aliases=[])
    skill_b = Skill(slug="graphql", label="GraphQL", category="tool", aliases=[])
    db_session.add_all([skill_a, skill_b])
    await db_session.flush()

    match1 = JobMatch(user_id=user.id, job_id=job1.id, scorer_version="v1", status="ready")
    match2 = JobMatch(user_id=user.id, job_id=job2.id, scorer_version="v1", status="ready")
    db_session.add_all([match1, match2])
    await db_session.flush()

    # Skill A gapped in BOTH matches (important + critical); Skill B in ONE.
    db_session.add_all(
        [
            SkillGap(
                user_id=user.id, scope="job", job_match_id=match1.id,
                skill_id=skill_a.id, skill_slug="kubernetes", skill_label="Kubernetes",
                severity="important",
            ),
            SkillGap(
                user_id=user.id, scope="job", job_match_id=match2.id,
                skill_id=skill_a.id, skill_slug="kubernetes", skill_label="Kubernetes",
                severity="critical",
            ),
            SkillGap(
                user_id=user.id, scope="job", job_match_id=match1.id,
                skill_id=skill_b.id, skill_slug="graphql", skill_label="GraphQL",
                severity="nice_to_have",
            ),
        ]
    )
    await db_session.flush()
    return user, skill_a, skill_b


async def test_aggregate_skill_gaps_rollup_and_idempotency(db_session):
    user, skill_a, skill_b = await _seed(db_session)
    svc = MatchService(db_session)

    made = await svc.aggregate_skill_gaps(user.id)

    assert len(made) == 2
    assert await _agg_count(db_session, user.id) == 2
    by_skill = {row.skill_id: row for row in made}

    agg_a = by_skill[skill_a.id]
    assert agg_a.scope == "aggregate"
    assert agg_a.job_match_id is None
    assert agg_a.frequency == 2
    assert agg_a.severity == "critical"  # most-severe of important + critical
    assert agg_a.rationale == "Missing in 2 of your job matches."

    agg_b = by_skill[skill_b.id]
    assert agg_b.frequency == 1
    assert agg_b.severity == "nice_to_have"

    # Delete-then-insert: re-running yields exactly 2 again, no duplicates.
    remade = await svc.aggregate_skill_gaps(user.id)
    assert len(remade) == 2
    assert await _agg_count(db_session, user.id) == 2
