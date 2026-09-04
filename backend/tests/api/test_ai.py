"""``/ai`` API — sessions, messages (SSE), goal, events, stop, actions.

DB + Redis integration; CI-deferred. These exercise real Postgres and a real
Redis pub/sub channel (the SSE cases publish a synthetic ``done`` frame to drive
``_relay`` to completion in the absence of a running ``run_agent`` worker).
"""

from __future__ import annotations

import json
import uuid

import pytest


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


async def test_relay_yields_open_then_relays_until_done():
    # `_relay` at the generator level — drive it by hand so the subscribe
    # happens (first __anext__) before we publish the terminal frame. The ASGI
    # test transport buffers response bodies, so a frame-by-frame test through
    # `client.stream(...)` would deadlock; this is transport-independent.
    from app.api.v1.ai import _relay
    from app.core.config import get_settings
    from app.core.redis import redis_from_settings

    redis = redis_from_settings(get_settings())
    channel = f"sse:ai:test-{uuid.uuid4().hex}"
    gen = _relay(redis, channel, run_id="run-xyz")
    try:
        first = await gen.__anext__()
        assert first.event == "open"
        assert json.loads(first.data)["run_id"] == "run-xyz"

        await redis.publish(
            channel,
            json.dumps({"event": "done", "status": "completed", "totals": {}}),
        )
        second = await gen.__anext__()
        assert second.event == "done"
        assert json.loads(second.data)["status"] == "completed"

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    finally:
        await gen.aclose()


async def test_post_message_starts_a_run_and_streams(client, db_session, monkeypatch):
    # Swap the unbounded relay for a two-frame finite generator so the buffering
    # ASGI test transport can drain POST /messages; assert the route composed
    # the run (session -> running with a run_id) before handing off to the stream.
    from app.core.events import sse_event

    async def _finite_relay(_redis, _channel, *, run_id=None):
        yield sse_event({"event": "open", "run_id": run_id})
        yield sse_event({"event": "done", "status": "completed"})

    monkeypatch.setattr("app.api.v1.ai._relay", _finite_relay)

    h = await _auth(client, "ai-msg@x.com")
    sid = await _new_session(client, h)
    r = await client.post(
        f"/api/v1/ai/sessions/{sid}/messages",
        headers=h,
        json={"content": "find jobs that match my experience"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in r.text

    row = (await client.get(f"/api/v1/ai/sessions/{sid}", headers=h)).json()
    assert row["run_id"] and row["status"] == "running"


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
