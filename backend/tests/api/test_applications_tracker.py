"""/applications tracker routes -- DB integration, CI-deferred."""
from __future__ import annotations

from app.models.job import Job


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


async def test_save_intent_creates_a_saved_application(client, db_session):
    h = await _auth(client, "tr-save@x.com")
    job = await _seed_job(db_session)
    r = await client.post(
        "/api/v1/applications", headers=h, json={"job_id": str(job.id), "intent": "save"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "saved" and body["source"] == "user"


async def test_list_patch_timeline_note_delete_round_trip(client, db_session):
    h = await _auth(client, "tr-full@x.com")
    job = await _seed_job(db_session)
    created = (
        await client.post(
            "/api/v1/applications", headers=h,
            json={"job_id": str(job.id), "intent": "save"},
        )
    ).json()
    app_id = created["id"]

    lst = await client.get("/api/v1/applications", headers=h)
    assert lst.status_code == 200 and lst.json()["total"] == 1

    patched = await client.patch(
        f"/api/v1/applications/{app_id}", headers=h, json={"status": "applied"}
    )
    assert patched.status_code == 200 and patched.json()["status"] == "applied"
    assert patched.json()["applied_at"] is not None

    bad = await client.patch(
        f"/api/v1/applications/{app_id}", headers=h, json={"status": "awaiting_approval"}
    )
    assert bad.status_code == 422 or bad.status_code == 400

    note = await client.post(
        f"/api/v1/applications/{app_id}/notes", headers=h, json={"body": "Recruiter replied"}
    )
    assert note.status_code == 201 and note.json()["kind"] == "note"

    tl = await client.get(f"/api/v1/applications/{app_id}/timeline", headers=h)
    assert tl.status_code == 200
    kinds = [it["kind"] for it in tl.json()["items"]]
    assert "status_change" in kinds and "note" in kinds

    dele = await client.delete(f"/api/v1/applications/{app_id}", headers=h)
    assert dele.status_code == 204
    gone = await client.get(f"/api/v1/applications/{app_id}", headers=h)
    assert gone.status_code == 404


async def test_list_filters_by_status_and_hides_deleted(client, db_session):
    h = await _auth(client, "tr-filter@x.com")
    job = await _seed_job(db_session)
    a1 = (
        await client.post(
            "/api/v1/applications", headers=h, json={"job_id": str(job.id), "intent": "save"}
        )
    ).json()
    a2 = (
        await client.post(
            "/api/v1/applications", headers=h, json={"job_id": str(job.id), "intent": "save"}
        )
    ).json()
    await client.patch(f"/api/v1/applications/{a1['id']}", headers=h, json={"status": "interview"})

    only_interview = await client.get("/api/v1/applications?status=interview", headers=h)
    ids = {it["id"] for it in only_interview.json()["items"]}
    assert ids == {a1["id"]}

    await client.delete(f"/api/v1/applications/{a2['id']}", headers=h)
    all_ = await client.get("/api/v1/applications", headers=h)
    assert {it["id"] for it in all_.json()["items"]} == {a1["id"]}
