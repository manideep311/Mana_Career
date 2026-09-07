"""GET /insights -- DB integration, CI-deferred."""
from __future__ import annotations

from sqlalchemy import select

from app.models.job import Job
from app.models.match import JobMatch, SkillGap
from app.models.skill import Skill
from app.models.user import User

_KEYS = {
    "strengths",
    "skills_to_develop",
    "recommended_next_step",
    "trending_skills",
    "suggested_projects",
    "roadmap_summary",
}


async def _auth(client, email):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_get_insights_fresh_user_returns_all_sections(client, db_session):
    h = await _auth(client, "insights-fresh@x.com")

    r = await client.get("/api/v1/insights", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert _KEYS <= set(body)
    assert body["strengths"] == []
    assert body["skills_to_develop"] == []
    assert body["suggested_projects"] == []
    assert body["roadmap_summary"] is None

    nba = body["recommended_next_step"]
    assert nba is None or {"kind", "title", "reason"} <= set(nba)


async def test_get_insights_fires_lazy_aggregate_rollup(client, db_session):
    email = "insights-rollup@x.com"
    h = await _auth(client, email)
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()

    job = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(job)
    await db_session.flush()

    match = JobMatch(
        user_id=user.id, job_id=job.id, scorer_version="v1", status="ready",
    )
    skill = Skill(slug="terraform", label="Terraform", category="tool", aliases=[])
    db_session.add_all([match, skill])
    await db_session.flush()

    db_session.add(
        SkillGap(
            user_id=user.id, scope="job", job_match_id=match.id, skill_id=skill.id,
            skill_slug="terraform", skill_label="Terraform", severity="critical",
            frequency=1, status="open",
        )
    )
    await db_session.flush()

    # No aggregate rows exist yet -- the route must roll them up on the fly.
    r = await client.get("/api/v1/insights", headers=h)
    assert r.status_code == 200
    develop = r.json()["skills_to_develop"]
    assert develop
    assert develop[0]["skill_slug"] == "terraform"
    assert develop[0]["scope"] == "aggregate"
