from __future__ import annotations

import decimal
import uuid

from sqlalchemy import select

from app.models.job import Job
from app.models.profile import CareerProfile
from app.models.user import User


async def _auth(client, email="matches-api@x.com"):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed(db_session, email: str) -> tuple[User, Job]:
    """User + CareerProfile + a visible, ready seed Job — mirrors
    tests/domain/matching/test_service.py::_seed, adapted for the API client."""
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    db_session.add(
        CareerProfile(
            user_id=user.id, seniority="senior", years_experience=decimal.Decimal("6")
        )
    )
    job = Job(
        user_id=None,
        is_seed=True,
        source="seed",
        status="ready",
        raw_text="x" * 60,
        title="Senior ML Engineer",
    )
    db_session.add(job)
    await db_session.commit()
    return user, job


async def test_create_match_returns_202_scoring(client, db_session):
    h = await _auth(client, "matches-create@x.com")
    _user, job = await _seed(db_session, "matches-create@x.com")
    r = await client.post("/api/v1/matches", headers=h, json={"job_id": str(job.id)})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "scoring" and uuid.UUID(body["id"])


async def test_get_match_shape_before_worker(client, db_session):
    h = await _auth(client, "matches-detail@x.com")
    _user, job = await _seed(db_session, "matches-detail@x.com")
    mid = (
        await client.post("/api/v1/matches", headers=h, json={"job_id": str(job.id)})
    ).json()["id"]
    r = await client.get(f"/api/v1/matches/{mid}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == mid
    assert body["job_id"] == str(job.id)
    assert body["status"] == "scoring"
    assert body["score"] is None
    assert body["band"] is None
    assert body["dimension_scores"] == {}
    assert body["strengths"] == [] and body["gaps"] == []
    assert body["explanation"] is None and body["computed_at"] is None


async def test_list_matches_returns_items(client, db_session):
    h = await _auth(client, "matches-list@x.com")
    _user, job = await _seed(db_session, "matches-list@x.com")
    await client.post("/api/v1/matches", headers=h, json={"job_id": str(job.id)})
    r = await client.get("/api/v1/matches", headers=h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert isinstance(items, list) and len(items) == 1
    assert items[0]["job_id"] == str(job.id)


async def test_recompute_all_returns_202_queued(client, db_session):
    h = await _auth(client, "matches-recompute@x.com")
    await _seed(db_session, "matches-recompute@x.com")
    r = await client.post(
        "/api/v1/matches/recompute", headers=h, json={"scope": "all"}
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and body["count"] >= 0


async def test_create_match_unknown_job_is_404(client, db_session):
    h = await _auth(client, "matches-404@x.com")
    await _seed(db_session, "matches-404@x.com")
    r = await client.post(
        "/api/v1/matches", headers=h, json={"job_id": str(uuid.uuid4())}
    )
    assert r.status_code == 404
