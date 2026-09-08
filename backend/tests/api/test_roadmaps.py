"""/roadmaps API -- DB integration, CI-deferred.

Exercises create (202 + enqueue stubbed by the autouse ``_no_enqueue``
fixture), list, detail-with-milestones, status patch, and the milestone
patch that closes the matching aggregate skill-gap row. Also checks the
``RoadmapPatchIn`` pattern rejects an out-of-range status with 422.
"""
from __future__ import annotations

import contextlib

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


@contextlib.asynccontextmanager
async def _pinned_session(session):
    """Seam for ``AsyncSessionLocal`` -- hand the route's short-lived session
    blocks the rolled-back test session so they see rows seeded in it."""
    yield session


async def _seed_learning_resources(db_session):
    sql_res = LearningResource(
        title="SQL Fundamentals", provider="Mode", type="course",
        url="https://example.com/roadmaps-api-test-lr-sql", skills=["sql"],
        level="beginner", cost="free",
        summary="Query relational data with confidence.", is_active=True,
    )
    rust_res = LearningResource(
        title="Rust in Anger", provider="No Starch", type="book",
        url="https://example.com/roadmaps-api-test-lr-rust", skills=["rust"],
        level="advanced", cost="paid",
        summary="Systems programming without the footguns.", is_active=True,
    )
    db_session.add_all([sql_res, rust_res])
    await db_session.commit()
    return sql_res, rust_res


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

    # Capture the ids before expire_all() -- afterwards, touching `gap.id` /
    # `rec.id` on the expired instances would fire a sync refresh outside the
    # async greenlet (MissingGreenlet).
    rec_id, gap_id = rec.id, gap.id
    db_session.expire_all()
    gap_row = (
        await db_session.execute(select(SkillGap).where(SkillGap.id == gap_id))
    ).scalar_one()
    assert gap_row.status == "closed"
    assert gap_row.addressed_by_roadmap_id == rec_id


async def test_patch_roadmap_rejects_bad_status(client, db_session):
    email = "roadmap-badstatus@x.com"
    h = await _auth(client, email)
    _user, rec, _milestone, _gap = await _seed_roadmap(db_session, email)

    r = await client.patch(
        f"/api/v1/roadmaps/{rec.id}", headers=h, json={"status": "planning"}
    )
    assert r.status_code == 422


async def test_roadmap_events_streams_for_owner_and_404s_non_owner(
    client, db_session, monkeypatch
):
    email = "roadmap-events@x.com"
    h = await _auth(client, email)
    _user, rec, _milestone, _gap = await _seed_roadmap(db_session, email)

    # Pin the route's short-lived sessions to the rolled-back test session and
    # swap the unbounded Redis relay for a single ``open`` frame so the buffering
    # ASGI test transport can drain the body (see ``sse-tests-asgitransport-buffers``).
    async def _open_only(_redis, _channel, *, terminal):
        yield {"event": "open"}

    monkeypatch.setattr(
        "app.api.v1.roadmaps.AsyncSessionLocal", lambda: _pinned_session(db_session)
    )
    monkeypatch.setattr("app.api.v1.roadmaps.status_stream", _open_only)

    r = await client.get(f"/api/v1/roadmaps/{rec.id}/events", headers=h)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    # the ``open`` frame drives the replay: milestone(s) then a terminal ``done``
    # because the seeded roadmap is already ``active``.
    assert "event: milestone" in r.text
    assert "event: done" in r.text

    other = await _auth(client, "roadmap-events-other@x.com")
    r2 = await client.get(f"/api/v1/roadmaps/{rec.id}/events", headers=other)
    assert r2.status_code == 404


async def test_learning_resources_filter_by_skills_and_level(client, db_session):
    h = await _auth(client, "learning-resources@x.com")
    await _seed_learning_resources(db_session)

    by_skill = await client.get(
        "/api/v1/learning-resources", headers=h, params={"skills": "sql"}
    )
    assert by_skill.status_code == 200
    assert {row["title"] for row in by_skill.json()} == {"SQL Fundamentals"}

    by_level = await client.get(
        "/api/v1/learning-resources", headers=h, params={"level": "beginner"}
    )
    assert by_level.status_code == 200
    assert {row["title"] for row in by_level.json()} == {"SQL Fundamentals"}
