"""Retry policy shared by every ARQ task.

ARQ only re-queues a job when it raises :class:`arq.worker.Retry` (or is
cancelled). Any other exception marks the job failed immediately, so a task
that merely re-raises on an early attempt is never retried and never reaches
its terminal-failure branch. Tasks use :func:`retry_or_fail` instead:

- a transient error on a non-final attempt raises ``Retry`` with exponential
  backoff;
- a permanent error, or the final attempt, returns so the caller records an
  explicit failure state, notifies the UI and writes a dead-letter record.
"""

from __future__ import annotations

from typing import Any, NoReturn

from arq.worker import Retry

from app.core.errors import (
    AuthError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.core.logging import get_logger

log = get_logger("worker.retry")

MAX_TRIES = 3
BASE_DELAY_SECONDS = 5
MAX_DELAY_SECONDS = 60

# Deterministic domain failures: another attempt would fail the same way.
# (LLM transport errors arrive as AppError("llm.upstream_error") and stay
# retryable.)
_PERMANENT = (ValidationAppError, NotFoundError, ConflictError, AuthError, ForbiddenError)


def attempt(ctx: dict[str, Any]) -> int:
    return int(ctx.get("job_try") or 1)


def backoff_seconds(job_try: int) -> int:
    """5 s, 10 s, 20 s, ... capped at 60 s (``job_try`` is 1-based)."""
    return int(min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2 ** max(0, job_try - 1)))


def is_retryable(exc: BaseException) -> bool:
    return not isinstance(exc, _PERMANENT)


def retry_or_fail(ctx: dict[str, Any], exc: BaseException, *, task: str) -> None:
    """Raise ``Retry`` for a transient error on a non-final attempt.

    Returns normally when the caller must record a terminal failure: the error
    is permanent or this was the last attempt.
    """
    job_try = attempt(ctx)
    if job_try >= MAX_TRIES or not is_retryable(exc):
        log.warning(
            "task_giving_up",
            task=task,
            attempt=job_try,
            max_tries=MAX_TRIES,
            permanent=not is_retryable(exc),
            error=repr(exc),
        )
        return
    _raise_retry(task, job_try, exc)


def _raise_retry(task: str, job_try: int, exc: BaseException) -> NoReturn:
    delay = backoff_seconds(job_try)
    log.warning(
        "task_retrying",
        task=task,
        attempt=job_try,
        max_tries=MAX_TRIES,
        retry_in_seconds=delay,
        error=repr(exc),
    )
    raise Retry(defer=delay) from exc
