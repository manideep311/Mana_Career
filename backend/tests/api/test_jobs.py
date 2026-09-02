import decimal
import uuid

from sqlalchemy import select

from app.domain.matching.weights import SCORER_VERSION
from app.models.job import Job
from app.models.match import JobMatch
from app.models.user import User


async def _auth(client, email="jobs-api@x.com"):
    await client.post("/api/v1/auth/register",
                      json={"email": email, "password": "pw12345678", "full_name": "J"})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw12345678"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_post_jobs_rejects_short_text(client):
    h = await _auth(client)
    r = await client.post("/api/v1/jobs", headers=h, json={"raw_text": "too short"})
    assert r.status_code == 422


async def test_post_jobs_accepts_and_returns_202(client):
    h = await _auth(client, "jobs-api2@x.com")
    r = await client.post("/api/v1/jobs", headers=h,
                          json={"raw_text": "Senior ML Engineer at Acme. " + "detail " * 20})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "ingesting" and uuid.UUID(body["id"])


async def test_get_jobs_lists_ready_seed_jobs_with_filters(client, db_session):
    h = await _auth(client, "jobs-api3@x.com")
    db_session.add_all([
        Job(user_id=None, is_seed=True, source="seed", status="ready",
            raw_text="x" * 60, title="Remote Rust Engineer", company="Foo", work_mode="remote"),
        Job(user_id=None, is_seed=True, source="seed", status="ready",
            raw_text="x" * 60, title="Onsite React Engineer", company="Bar", work_mode="onsite"),
        Job(user_id=None, is_seed=True, source="seed", status="ingesting",
            raw_text="x" * 60, title="Hidden", company="Baz"),
    ])
    await db_session.commit()
    r = await client.get("/api/v1/jobs", headers=h)
    titles = {j["title"] for j in r.json()["items"]}
    assert "Remote Rust Engineer" in titles and "Onsite React Engineer" in titles
    assert "Hidden" not in titles
    r = await client.get("/api/v1/jobs?work_mode=remote", headers=h)
    assert {j["title"] for j in r.json()["items"]} == {"Remote Rust Engineer"}
    r = await client.get("/api/v1/jobs?q=react", headers=h)
    assert {j["title"] for j in r.json()["items"]} == {"Onsite React Engineer"}


async def test_get_job_detail_has_raw_text(client, db_session):
    h = await _auth(client, "jobs-api5@x.com")
    job = Job(user_id=None, is_seed=True, source="seed", status="ready",
              raw_text="y" * 80, title="Detail Job", company="Cee")
    db_session.add(job)
    await db_session.commit()
    r = await client.get(f"/api/v1/jobs/{job.id}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["raw_text"] == "y" * 80
    assert body["title"] == "Detail Job"
    assert body["required_skills"] == [] and body["preferred_skills"] == []
    assert body["responsibilities"] == []


async def test_get_jobs_surfaces_match_score_has_match_filter_and_sort(client, db_session):
    email = "jobs-api-match@x.com"
    h = await _auth(client, email)
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    matched = Job(user_id=None, is_seed=True, source="seed", status="ready",
                  raw_text="x" * 60, title="Matched Job", company="M")
    unmatched = Job(user_id=None, is_seed=True, source="seed", status="ready",
                    raw_text="x" * 60, title="Unmatched Job", company="U")
    db_session.add_all([matched, unmatched])
    await db_session.flush()
    db_session.add(JobMatch(
        user_id=user.id, job_id=matched.id, scorer_version=SCORER_VERSION,
        resume_version_id=None, status="ready",
        score=decimal.Decimal("88"), band="good",
    ))
    await db_session.commit()

    # match score/band/status land on the card
    r = await client.get("/api/v1/jobs", headers=h)
    cards = {j["title"]: j for j in r.json()["items"]}
    assert cards["Matched Job"]["match_score"] == 88.0
    assert cards["Matched Job"]["match_band"] == "good"
    assert cards["Matched Job"]["match_status"] == "ready"
    assert cards["Unmatched Job"]["match_score"] is None
    assert cards["Unmatched Job"]["match_band"] is None
    assert cards["Unmatched Job"]["match_status"] is None

    # has_match=true keeps only jobs with a ready match
    r = await client.get("/api/v1/jobs?has_match=true", headers=h)
    titles = {j["title"] for j in r.json()["items"]}
    assert "Matched Job" in titles
    assert "Unmatched Job" not in titles

    # sort=match orders the matched job ahead of the unmatched one
    r = await client.get("/api/v1/jobs?sort=match", headers=h)
    ordered = [j["title"] for j in r.json()["items"]]
    assert ordered.index("Matched Job") < ordered.index("Unmatched Job")


async def test_delete_seed_job_is_404(client, db_session):
    h = await _auth(client, "jobs-api4@x.com")
    job = Job(user_id=None, is_seed=True, source="seed", status="ready",
              raw_text="x" * 60, title="S")
    db_session.add(job)
    await db_session.commit()
    r = await client.delete(f"/api/v1/jobs/{job.id}", headers=h)
    assert r.status_code == 404
