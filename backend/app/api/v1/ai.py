from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Response, status
from redis.asyncio import Redis
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.v1.schemas.ai import (
    AiActionListOut,
    AiActionOut,
    GoalIn,
    MessageIn,
    MessageOut,
    RunRefOut,
    SessionCreateIn,
    SessionListOut,
    SessionOut,
    SessionSummaryOut,
)
from app.core.errors import NotFoundError
from app.core.events import sse_event
from app.domain.agents.service import AgentService
from app.models.ai import AiAction, AiSession, Message

router = APIRouter(prefix="/ai", tags=["ai"])


# --------------------------------------------------------------------------- #
# mappers (explicit — no `from_attributes`)
# --------------------------------------------------------------------------- #
def _message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        blocks=list(m.blocks),
        created_at=m.created_at,
    )


def _session_summary_out(s: AiSession) -> SessionSummaryOut:
    return SessionSummaryOut(
        id=s.id,
        kind=s.kind,
        goal=s.goal,
        title=s.title,
        status=s.status,
        run_id=s.run_id,
        totals=dict(s.totals or {}),
        error=s.error,
        created_at=s.created_at,
        started_at=s.started_at,
        ended_at=s.ended_at,
    )


def _session_out(s: AiSession, *, messages: list[MessageOut]) -> SessionOut:
    return SessionOut(**_session_summary_out(s).model_dump(), messages=messages)


def _action_out(a: AiAction) -> AiActionOut:
    return AiActionOut(
        id=a.id,
        ai_session_id=a.ai_session_id,
        run_id=a.run_id,
        node=a.node,
        action_key=a.action_key,
        summary=a.summary,
        status=a.status,
        entity_type=a.entity_type,
        entity_id=a.entity_id,
        occurred_at=a.occurred_at,
    )


# --------------------------------------------------------------------------- #
# SSE relay — a thin local variant of `app.core.events.status_stream`, keyed on
# the worker's `event == "done"` sentinel instead of a status set. Bounded by a
# hard wall-clock cap so an abandoned stream (a client that opened `/events` or
# `/messages` and vanished without the disconnect propagating) can never pin a
# subscription forever — a run's own deadline is 180s, so 300s is dead.
# --------------------------------------------------------------------------- #
_RELAY_MAX_SECONDS = 300.0


async def _relay(
    redis: Redis, channel: str, *, run_id: str | None = None
) -> AsyncIterator[ServerSentEvent]:
    pubsub = redis.pubsub()  # no I/O until subscribe()
    deadline = asyncio.get_running_loop().time() + _RELAY_MAX_SECONDS
    open_frame: dict[str, Any] = {"event": "open"}
    if run_id is not None:
        open_frame["run_id"] = run_id
    try:
        await pubsub.subscribe(channel)
        yield sse_event(open_frame)  # only after the subscription is live
        while asyncio.get_running_loop().time() < deadline:
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=5.0
            )
            if msg is None:
                # EventSourceResponse emits its own keepalive comments.
                continue
            try:
                payload: dict[str, Any] = json.loads(msg["data"])
            except (json.JSONDecodeError, TypeError):
                yield sse_event(
                    {"event": "error", "message": "Malformed stream payload."}
                )
                return
            yield sse_event(payload)
            if payload.get("event") == "done":
                return
        # Cap reached with no terminal frame — close the stream cleanly.
        yield sse_event({"event": "done", "status": "timeout", "totals": {}})
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #
@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreateIn, db: DbDep, user: CurrentUser
) -> SessionOut:
    s = await AgentService(db).create_session(
        user.id, kind=body.kind, context=body.context
    )
    return _session_out(s, messages=[])


@router.get("/sessions")
async def list_sessions(
    db: DbDep, user: CurrentUser, limit: int = 20, offset: int = 0
) -> SessionListOut:
    rows, total = await AgentService(db).list_sessions(
        user.id, limit=limit, offset=offset
    )
    return SessionListOut(
        items=[_session_summary_out(s) for s in rows], total=total
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> SessionOut:
    svc = AgentService(db)
    s = await svc.get_session(user.id, session_id)
    messages = [_message_out(m) for m in await svc.recent_messages(session_id)]
    return _session_out(s, messages=messages)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: uuid.UUID,
    body: MessageIn,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> EventSourceResponse:
    svc = AgentService(db)
    await svc.get_session(user.id, session_id)  # ownership / 404 guard
    await svc.add_user_message(user.id, session_id, body.content)
    goal, inputs = svc.infer_goal(body.content)
    run_id = await svc.start_run(user.id, session_id, goal=goal, inputs=inputs)
    # The SSE body outlives the request-scoped autocommit, so persist now.
    await db.commit()
    return EventSourceResponse(_relay(redis, f"sse:ai:{run_id}", run_id=run_id))


@router.post("/sessions/{session_id}/goal", status_code=status.HTTP_202_ACCEPTED)
async def post_goal(
    session_id: uuid.UUID, body: GoalIn, db: DbDep, user: CurrentUser
) -> RunRefOut:
    run_id = await AgentService(db).start_run(
        user.id, session_id, goal=body.goal, inputs=body.inputs
    )
    await db.commit()
    return RunRefOut(run_id=run_id, session_id=str(session_id))


@router.get("/sessions/{session_id}/events")
async def session_events(
    session_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    run_id: str | None = None,
) -> EventSourceResponse:
    rid = run_id or (await AgentService(db).get_session(user.id, session_id)).run_id
    if not rid:
        raise NotFoundError("No run for this session")
    return EventSourceResponse(_relay(redis, f"sse:ai:{rid}", run_id=rid))


@router.post("/sessions/{session_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_run(
    session_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> Response:
    await AgentService(db).stop_run(user.id, session_id)
    await db.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


# --------------------------------------------------------------------------- #
# action log (human-readable)
# --------------------------------------------------------------------------- #
@router.get("/actions")
async def list_actions(
    db: DbDep,
    user: CurrentUser,
    session_id: uuid.UUID | None = None,
    limit: int = 30,
    offset: int = 0,
) -> AiActionListOut:
    rows, total = await AgentService(db).list_actions(
        user.id, session_id=session_id, limit=limit, offset=offset
    )
    return AiActionListOut(items=[_action_out(a) for a in rows], total=total)
