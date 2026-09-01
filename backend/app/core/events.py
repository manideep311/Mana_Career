from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis
from sse_starlette import ServerSentEvent


def resume_channel(resume_id: str) -> str:
    return f"sse:resume:{resume_id}"


async def publish_status(
    redis: Redis,
    channel: str,
    *,
    resource: str,
    id: str,
    status: str,
    message: str | None = None,
) -> None:
    await redis.publish(
        channel,
        json.dumps(
            {
                "event": "status",
                "resource": resource,
                "id": id,
                "status": status,
                "message": message,
            }
        ),
    )


async def status_stream(
    redis: Redis,
    channel: str,
    *,
    terminal: set[str],
) -> AsyncIterator[dict[str, Any]]:
    pubsub = redis.pubsub()  # no I/O until subscribe()
    try:
        await pubsub.subscribe(channel)
        yield {"event": "open"}  # only fires once the subscription is live
        while True:
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=15.0
            )
            if msg is None:
                # EventSourceResponse sends its own keepalive comment; nothing
                # to emit on a plain read timeout.
                continue
            try:
                payload: dict[str, Any] = json.loads(msg["data"])
            except (json.JSONDecodeError, TypeError):
                yield {
                    "event": "error",
                    "code": "stream.bad_payload",
                    "message": "Received a malformed status update.",
                }
                return
            yield payload
            if payload.get("status") in terminal:
                yield {
                    "event": "done",
                    "status": payload.get("status"),
                    "totals": {},
                }
                return
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]


def sse_event(payload: dict[str, Any]) -> ServerSentEvent:
    return ServerSentEvent(event=payload.get("event", "status"), data=json.dumps(payload))
