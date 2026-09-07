"""/roadmaps API -- DB integration, CI-deferred.

Exercises create (202 + enqueue stubbed by the autouse ``_no_enqueue``
fixture), list, detail-with-milestones, status patch, and the milestone
patch that closes the matching aggregate skill-gap row. Also checks the
``RoadmapPatchIn`` pattern rejects an out-of-range status with 422.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.learning import (
    LearningRecommendation,
    LearningResource,
    RoadmapMilestone,
)
from app.models.match import SkillGap
from app.models.skill import Skill
from app.models.user import User


async def _auth(client, email):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed_roadmap(db_session, email):
    """User (already registered by ``_auth``) + a Skill + an aggregate open
    SkillGap + a LearningResource + a ``planning`` LearningRecommendation with
    one milestone whose ``skill_slug`` matches the gap."""
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()

    skill = Skill(slug="kubernetes", label="Kubernetes", category="tool", aliases=[])
    resource = LearningResource(
        title="Kubernetes the Hard Way",
        provider="Google",
        url="https://example.com/roadmaps-api-test-k8s",
        type="course",
        skills=["kubernetes"],
        level="intermediate",
        cost="free",
        summary="Bootstrap a cluster by hand to learn every moving part.",
        embedding=[0.1] * 1024,
    )
    db_session.add_all([skill, resource])
    await db_session.flush()

    gap = SkillGap(
        user_id=user.id,
        scope="aggregate",
        skill_id=skill.id,
        skill_slug="kubernetes",
        skill_label="Kubernetes",
        severity="critical",
        frequency=2,
        status="open",
    )
    rec = LearningRecommendation(
        user_id=user.id,
        scope="aggregate",
        title="Close your top skill gaps",
        constraints={},
        status="active",
        generation_meta={},
    )
    db_session.add_all([gap, rec])
    await db_session.flush()

    milestone = RoadmapMilestone(
        recommendation_id=rec.id,
        user_id=user.id,
        order_index=0,
        skill_slug="kubernetes",
        skill_label="Kubernetes",
        title="Stand up a cluster",
        why_it_matters="Every deploy target runs on one.",
        resource_ids=[resource.id],
        est_hours=12,
        status="not_started",
    )
    db_session.add(milestone)
    await db_session.commit()
    return user, rec, milestone, gap


async def test_create_roadmap_returns_202_with_id(client, db_session):
    h = await _auth(client, "roadmap-create@x.com")
    r = await client.post("/api/v1/roadmaps", headers=h, json={})
    assert r.status_code == 202
    assert "id" in r.json()


async def test_list_get_and_patches(client, db_session):
    email = "roadmap-flow@x.com"
    h = await _auth(client, email)
    _user, rec, milestone, gap = await _seed_roadmap(db_session, email)

    listed = await client.get("/api/v1/roadmaps", headers=h)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert str(rec.id) in {item["id"] for item in items}

    detail = await client.get(f"/api/v1/roadmaps/{rec.id}", headers=h)
    assert detail.status_code == 200
    body = detail.json()
    assert isinstance(body["milestones"], list) and len(body["milestones"]) == 1
    assert body["milestones"][0]["skill_slug"] == "kubernetes"
    assert body["milestones"][0]["resource_ids"] == [
        str(rid) for rid in milestone.resource_ids
    ]

    archived = await client.patch(
        f"/api/v1/roadmaps/{rec.id}", headers=h, json={"status": "archived"}
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    done = await client.patch(
        f"/api/v1/roadmaps/{rec.id}/milestones/{milestone.id}",
        headers=h,
        json={"status": "done"},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "done"

    db_session.expire_all()
    gap_row = (
        await db_session.execute(select(SkillGap).where(SkillGap.id == gap.id))
    ).scalar_one()
    assert gap_row.status == "closed"
    assert gap_row.addressed_by_roadmap_id == rec.id


async def test_patch_roadmap_rejects_bad_status(client, db_session):
    email = "roadmap-badstatus@x.com"
    h = await _auth(client, email)
    _user, rec, _milestone, _gap = await _seed_roadmap(db_session, email)

    r = await client.patch(
        f"/api/v1/roadmaps/{rec.id}", headers=h, json={"status": "planning"}
    )
    assert r.status_code == 422
