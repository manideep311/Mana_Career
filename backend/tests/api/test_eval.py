from __future__ import annotations

from sqlalchemy import select

from app.models.user import User


async def _admin_auth(client, db_session, email="eval-admin@x.com"):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "A"},
    )
    u = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    u.is_admin = True
    await db_session.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_non_admin_gets_403(client, db_session):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "plain@x.com", "password": "correct-passphrase", "full_name": "P"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": "plain@x.com", "password": "correct-passphrase"}
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/api/v1/eval/runs", headers=h)).status_code == 403


async def test_create_run_then_list_and_fetch(client, db_session):
    h = await _admin_auth(client, db_session)

    created = await client.post(
        "/api/v1/eval/runs", headers=h, json={"suite": "retrieval"}
    )
    assert created.status_code == 202
    body = created.json()
    run_id = body["id"]
    assert body["suite"] == "retrieval"
    assert "recall_at_10" in body["metrics"]

    lst = await client.get("/api/v1/eval/runs", headers=h)
    assert lst.status_code == 200
    assert lst.json()["total"] >= 1

    detail = await client.get(f"/api/v1/eval/runs/{run_id}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["id"] == run_id

    results = await client.get(f"/api/v1/eval/runs/{run_id}/results", headers=h)
    assert results.status_code == 200
    assert len(results.json()) >= 15

    missing = await client.get(
        f"/api/v1/eval/runs/{'0' * 8}-0000-0000-0000-000000000000/results", headers=h
    )
    assert missing.status_code == 200
    assert missing.json() == []

    missing_run = await client.get(
        f"/api/v1/eval/runs/{'0' * 8}-0000-0000-0000-000000000000", headers=h
    )
    assert missing_run.status_code == 404
