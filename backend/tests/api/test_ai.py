"""``/ai`` API — sessions, messages (SSE), goal, events, stop, actions.

DB + Redis integration; CI-deferred. These exercise real Postgres and a real
Redis pub/sub channel (the SSE cases publish a synthetic ``done`` frame to drive
``_relay`` to completion in the absence of a running ``run_agent`` worker).
"""

from __future__ import annotations

import asyncio
import json
import uuid


async def _auth(client, email="ai-api@x.com"):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _new_session(client, headers) -> str:
    r = await client.post(
        "/api/v1/ai/sessions", headers=headers, json={"kind": "chat"}
    )
    assert r.status_code == 201
    return r.json()["id"]


async def test_create_session_returns_201_idle(client, db_session):
    h = await _auth(client, "ai-create@x.com")
    r = await client.post(
        "/api/v1/ai/sessions", headers=h, json={"kind": "chat"}
    )
    assert r.status_code == 201
    body = r.json()
    assert uuid.UUID(body["id"])
    assert body["kind"] == "chat"
    assert body["status"] == "idle"
    assert body["run_id"] is None
    assert body["messages"] == []


async def test_list_sessions_returns_total(client, db_session):
    h = await _auth(client, "ai-list@x.com")
    await _new_session(client, h)
    r = await client.get("/api/v1/ai/sessions", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list)
    assert body["total"] >= 1


async def test_post_message_streams_sse_open_then_done(client, db_session):
    from app.core.config import get_settings
    from app.core.redis import redis_from_settings

    h = await _auth(client, "ai-msg@x.com")
    sid = await _new_session(client, h)
    redis = redis_from_settings(get_settings())

    async def _run() -> list[str]:
        seen: list[str] = []
        async with client.stream(
            "POST",
            f"/api/v1/ai/sessions/{sid}/messages",
            headers=h,
            json={"content": "find jobs that match my experience"},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")

            # `run_id` is committed by the route before the response returns.
            row = (await client.get(f"/api/v1/ai/sessions/{sid}", headers=h)).json()
            assert row["run_id"]

            async for line in resp.aiter_lines():
                text = line.strip()
                if not text.startswith("event:"):
                    continue
                name = text.split(":", 1)[1].strip()
                seen.append(name)
                if name == "open":
                    # Subscription is live; stand in for the worker's terminal frame.
                    await redis.publish(
                        f"sse:ai:{row['run_id']}",
                        json.dumps(
                            {"event": "done", "status": "completed", "totals": {}}
                        ),
                    )
                if name == "done":
                    break
        return seen

    seen = await asyncio.wait_for(_run(), timeout=30)
    assert seen[0] == "open"
    assert "done" in seen


async def test_goal_returns_202_run_ref(client, db_session):
    h = await _auth(client, "ai-goal@x.com")
    sid = await _new_session(client, h)
    r = await client.post(
        f"/api/v1/ai/sessions/{sid}/goal",
        headers=h,
        json={"goal": "analyze_profile", "inputs": {}},
    )
    assert r.status_code == 202
    assert r.json()["run_id"]


async def test_list_actions_returns_list(client, db_session):
    h = await _auth(client, "ai-actions@x.com")
    r = await client.get("/api/v1/ai/actions", headers=h)
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


async def test_second_message_while_running_is_422(client, db_session):
    h = await _auth(client, "ai-busy@x.com")
    sid = await _new_session(client, h)

    # Start the first run via the goal endpoint (202, no streaming body to hold
    # open) so the session is left in `running` for the concurrency check.
    r1 = await client.post(
        f"/api/v1/ai/sessions/{sid}/goal",
        headers=h,
        json={"goal": "understand_job", "inputs": {}},
    )
    assert r1.status_code == 202

    r2 = await client.post(
        f"/api/v1/ai/sessions/{sid}/messages",
        headers=h,
        json={"content": "and again"},
    )
    assert r2.status_code == 422
