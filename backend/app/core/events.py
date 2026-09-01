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
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if msg is None:
                yield {"event": "ping"}
                continue
            payload: dict[str, Any] = json.loads(msg["data"])
            yield payload
            if payload.get("status") in terminal:
                return
    finally:
        # A mid-stream connection drop can make unsubscribe() raise; aclose() is
        # the call that releases the pooled connection, so it must still run.
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        # redis-py's async PubSub.aclose lacks type coverage under strict mypy.
        await pubsub.aclose()  # type: ignore[no-untyped-call]


def sse_event(payload: dict[str, Any]) -> ServerSentEvent:
    return ServerSentEvent(event=payload.get("event", "status"), data=json.dumps(payload))
