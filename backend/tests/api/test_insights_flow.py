"""End-to-end career-insights chain -- DB integration, CI-deferred.

One test walks the whole Phase 12a surface with the ``client`` + ``db_session``
fixtures and the autouse ``_no_enqueue`` patch:

    seed 2 matches + job-scoped gaps
      -> POST /skill-gaps/aggregate      (deterministic aggregate rollup)
      -> POST /roadmaps                  (202; LearningRecommendation in 'planning')
      -> RoadmapPlanner(...).plan(...)   (enqueue was stubbed -- drive it directly)
      -> GET  /roadmaps/{id}             (status 'active'; milestones [] under fake LLM)
      -> PATCH .../milestones/{mid}      (only if a milestone exists -> gap 'closed')
      -> GET  /insights                 (roadmap_summary populated; python in gaps)

Locally this ERRORs at the ``_migrated`` fixture (no Postgres); it runs green in CI.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.llm.factory import get_llm_provider
from app.domain.roadmap.planner import RoadmapPlanner
from app.models.job import Job
from app.models.learning import LearningResource
from app.models.match import JobMatch, SkillGap
from app.models.skill import Skill
from app.models.user import User

_INSIGHTS_KEYS = {
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


async def test_insights_end_to_end(client, db_session):
    email = "insights-flow@x.com"
    h = await _auth(client, email)
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()

    # --- seed: 1 skill, 2 seed jobs (both require python), 1 learning resource ---
    skill = Skill(slug="python", label="Python", category="language", aliases=[])
    db_session.add(skill)
    await db_session.flush()

    req = [{"skill_id": str(skill.id), "slug": "python", "label": "Python", "weight": 0.8}]
    job_a = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=req, preferred_skills=[],
    )
    job_b = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Platform Engineer", company="Globex", required_skills=req, preferred_skills=[],
    )
    resource = LearningResource(
        title="Python for Engineers",
        provider="Mana",
        url="https://example.com/insights-flow-test-python",
        type="course",
        skills=["python"],
        level="beginner",
        cost="free",
        summary="Ship production Python with confidence.",
        embedding=[0.0] * 1024,
        is_active=True,
    )
    db_session.add_all([job_a, job_b, resource])
    await db_session.flush()

    # --- seed: 2 JobMatch rows (1 per job) + a job-scoped SkillGap for each ------
    match_a = JobMatch(
        user_id=user.id, job_id=job_a.id, scorer_version="v1", status="ready",
        strengths=[{"dimension": "experience", "raw_score": 0.8, "contribution": 20.0}],
    )
    match_b = JobMatch(
        user_id=user.id, job_id=job_b.id, scorer_version="v1", status="ready",
        strengths=[{"dimension": "experience", "raw_score": 0.8, "contribution": 20.0}],
    )
    db_session.add_all([match_a, match_b])
    await db_session.flush()

    db_session.add_all(
        [
            SkillGap(
                user_id=user.id, scope="job", job_match_id=match_a.id, skill_id=skill.id,
                skill_slug="python", skill_label="Python", severity="important", frequency=1,
            ),
            SkillGap(
                user_id=user.id, scope="job", job_match_id=match_b.id, skill_id=skill.id,
                skill_slug="python", skill_label="Python", severity="critical", frequency=1,
            ),
        ]
    )
    await db_session.flush()

    # --- 1) aggregate rollup ---------------------------------------------------
    r = await client.post("/api/v1/skill-gaps/aggregate", headers=h)
    assert r.status_code == 200
    agg = r.json()
    assert len(agg) >= 1
    assert any(row["skill_slug"] == "python" for row in agg)

    # --- 2) create the roadmap (enqueue stubbed -> rec sits in 'planning') ----
    rr = await client.post("/api/v1/roadmaps", headers=h, json={})
    assert rr.status_code == 202
    rec_id = rr.json()["id"]

    # --- 3) drive the planner directly on the test session -------------------
    frames: list[dict] = []

    async def _collect(f):
        frames.append(f)

    s = get_settings()
    await RoadmapPlanner(
        db_session, llm=get_llm_provider(s), embeddings=get_embeddings_provider(s)
    ).plan(user.id, scope="aggregate", job_id=None, constraints={}, publish=_collect)
    assert frames and frames[-1]["event"] == "done"

    # --- 4) roadmap detail: 'active'; milestones [] under the fake LLM -------
    g = await client.get(f"/api/v1/roadmaps/{rec_id}", headers=h)
    assert g.status_code == 200
    body = g.json()
    assert body["status"] == "active"
    ms = body["milestones"]
    assert isinstance(ms, list)

    # --- 5) completing a milestone (if any) closes the aggregate gap --------
    if ms:
        pr = await client.patch(
            f"/api/v1/roadmaps/{rec_id}/milestones/{ms[0]['id']}",
            headers=h,
            json={"status": "done"},
        )
        assert pr.status_code == 200
        uid = user.id  # capture before expire_all() -- see test_roadmaps note
        db_session.expire_all()
        closed = (
            await db_session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == uid,
                    SkillGap.scope == "aggregate",
                    SkillGap.skill_slug == "python",
                )
            )
        ).scalars().all()
        assert closed and all(row.status == "closed" for row in closed)

    # --- 6) insights: every section, roadmap_summary populated, python gap --
    ins = await client.get("/api/v1/insights", headers=h)
    assert ins.status_code == 200
    j = ins.json()
    assert set(j) >= _INSIGHTS_KEYS
    assert j["roadmap_summary"] is not None
    assert j["strengths"]
    assert any(row["skill_slug"] == "python" for row in j["skills_to_develop"])
