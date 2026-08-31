from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

log = get_logger("worker.dead_letter")


async def record_failure(
    task_name: str, *, args: tuple[Any, ...], kwargs: dict[str, Any], error: BaseException
) -> None:
    """Structured record of a permanently failed task.

    A durable ``task_failures`` table lands in a later phase (spec 5.3); for now
    this is a structured log line (secret redaction already applies).
    """
    log.error(
        "task_failed",
        task=task_name,
        args=list(args),
        kwargs=kwargs,
        error=repr(error),
    )
