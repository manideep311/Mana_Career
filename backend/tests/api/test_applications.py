"""POST /applications + GET /applications/{id} -- DB integration, CI-deferred."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.job import Job
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


async def _seed_job(db_session) -> Job:
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    return j


async def test_get_application_not_found_for_another_user(client, db_session):
    h = await _auth(client, "app-owner@x.com")
    r = await client.get(f"/api/v1/applications/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404


async def test_create_application_returns_202_run_ref(client, db_session):
    h = await _auth(client, "app-create@x.com")
    job = await _seed_job(db_session)
    r = await client.post("/api/v1/applications", headers=h, json={"job_id": str(job.id)})
    assert r.status_code == 202
    body = r.json()
    assert body["run_id"]
    assert body["session_id"]


async def test_get_application_after_direct_insert(client, db_session):
    from app.models.application import Application

    h = await _auth(client, "app-read@x.com")
    user = (
        await db_session.execute(select(User).where(User.email == "app-read@x.com"))
    ).scalar_one()
    job = await _seed_job(db_session)
    application = Application(user_id=user.id, job_id=job.id)
    db_session.add(application)
    await db_session.flush()

    r = await client.get(f"/api/v1/applications/{application.id}", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "preparing"
