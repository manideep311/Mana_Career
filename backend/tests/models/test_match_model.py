import decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.job import Job
from app.models.match import JobMatch, MatchComponent, SkillGap
from app.models.skill import Skill
from app.models.user import User


async def _user_job(db_session, email="m@example.com"):
    u = User(email=email, password_hash="x", full_name="M")
    db_session.add(u)
    await db_session.flush()
    j = Job(user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60, title="J")
    db_session.add(j)
    await db_session.flush()
    return u, j


async def test_job_match_defaults_and_partial_unique(db_session):
    u, j = await _user_job(db_session)
    m = JobMatch(user_id=u.id, job_id=j.id, scorer_version="v1")
    db_session.add(m)
    await db_session.flush()
    got = (await db_session.execute(select(JobMatch).where(JobMatch.id == m.id))).scalar_one()
    assert got.status == "scoring"
    assert got.resume_version_id is None
    assert got.strengths == [] and got.gaps == [] and got.dimension_scores == {}
    # second current-profile row for the same (user, job, version) is rejected
    db_session.add(JobMatch(user_id=u.id, job_id=j.id, scorer_version="v1"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_match_component_dimension_check_and_unique(db_session):
    u, j = await _user_job(db_session, "m2@example.com")
    m = JobMatch(user_id=u.id, job_id=j.id, scorer_version="v1")
    db_session.add(m)
    await db_session.flush()
    db_session.add(MatchComponent(
        job_match_id=m.id, dimension="skill",
        raw_score=decimal.Decimal("0.900"), weight=decimal.Decimal("0.220"),
        contribution=decimal.Decimal("19.80"),
    ))
    await db_session.flush()
    db_session.add(MatchComponent(
        job_match_id=m.id, dimension="bogus",
        raw_score=decimal.Decimal("0.5"), weight=decimal.Decimal("0.1"),
        contribution=decimal.Decimal("5"),
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_skill_gap_severity_check_and_cascade(db_session):
    u, j = await _user_job(db_session, "m3@example.com")
    m = JobMatch(user_id=u.id, job_id=j.id, scorer_version="v1")
    s = Skill(slug="rust", label="Rust", category="language")
    db_session.add_all([m, s])
    await db_session.flush()
    g = SkillGap(
        user_id=u.id, scope="job", job_match_id=m.id, skill_id=s.id,
        skill_slug="rust", skill_label="Rust", severity="important",
    )
    db_session.add(g)
    await db_session.flush()
    assert g.status == "open" and g.frequency == 1
    g.severity = "bogus"
    with pytest.raises(IntegrityError):
        await db_session.flush()
