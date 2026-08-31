from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

log = get_logger("worker.ping")


async def ping(ctx: dict[str, Any], payload: str = "pong") -> dict[str, Any]:
    log.info("worker_ping", payload=payload, job_id=ctx.get("job_id"))
    return {"echo": payload, "job_id": ctx.get("job_id")}
