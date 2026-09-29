"""Real ARQ worker + real Redis: prove what actually gets retried.

These tests run a genuine ``arq.worker.Worker`` in burst mode. They exist
because an earlier test simulated retries by calling a task with different
``job_try`` values, which passed even though ARQ never re-ran anything: ARQ
only retries a job that raises ``arq.worker.Retry``.

Redis is required. Locally the tests skip when Redis is unreachable; in CI
(``CI`` is set) an unreachable Redis is a failure, never a skip.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from arq.worker import Worker

from app.worker import retry as retry_policy
from app.worker.retry import MAX_TRIES, retry_or_fail


@pytest.fixture
async def arq_pool(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[ArqRedis]:
    # Retry immediately so the burst worker doesn't sleep through backoff.
    monkeypatch.setattr(retry_policy, "BASE_DELAY_SECONDS", 0)
    settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379/1"))
    settings.conn_retries = 0
    queue = f"test:arq-retry:{uuid.uuid4().hex}"
    try:
        pool = await create_pool(settings, default_queue_name=queue)
        await pool.ping()
    except Exception as exc:  # any connection failure means "no Redis"
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Redis unavailable locally ({exc!r}); runs in CI")
    try:
        yield pool
    finally:
        await pool.delete(queue)
        await pool.aclose()


async def _run(pool: ArqRedis, fn: Callable[..., Awaitable[Any]]) -> Any:
    job = await pool.enqueue_job(fn.__name__)
    assert job is not None
    worker = Worker(
        functions=[fn],
        redis_pool=pool,
        burst=True,
        poll_delay=0.01,
        max_tries=MAX_TRIES,
        handle_signals=False,
        keep_result=60,
    )
    try:
        await worker.main()
    finally:
        await worker.close()
    return job


async def test_plain_exception_is_never_retried_by_arq(arq_pool: ArqRedis) -> None:
    """The original bug: re-raising an ordinary exception ends the job."""
    attempts: list[int] = []

    async def plain_raise(ctx: dict[str, Any]) -> None:
        attempts.append(ctx["job_try"])
        raise RuntimeError("transient failure")

    job = await _run(arq_pool, plain_raise)
    assert attempts == [1]
    with pytest.raises(RuntimeError):
        await job.result(timeout=5)


async def test_retry_policy_makes_arq_run_the_job_again(arq_pool: ArqRedis) -> None:
    attempts: list[int] = []

    async def flaky_then_ok(ctx: dict[str, Any]) -> str:
        attempts.append(ctx["job_try"])
        if ctx["job_try"] == 1:
            retry_or_fail(ctx, OSError("database connection reset"), task="flaky_then_ok")
        return "done"

    job = await _run(arq_pool, flaky_then_ok)
    assert attempts == [1, 2]
    assert await job.result(timeout=5) == "done"


async def test_persistent_failure_stops_at_max_tries_with_an_explicit_result(
    arq_pool: ArqRedis,
) -> None:
    attempts: list[int] = []

    async def always_down(ctx: dict[str, Any]) -> str:
        attempts.append(ctx["job_try"])
        retry_or_fail(ctx, OSError("still down"), task="always_down")
        # Final attempt: the task records its terminal failure state here.
        return "failed"

    job = await _run(arq_pool, always_down)
    assert attempts == list(range(1, MAX_TRIES + 1))
    assert await job.result(timeout=5) == "failed"


async def test_permanent_error_is_not_retried(arq_pool: ArqRedis) -> None:
    from app.core.errors import ValidationAppError

    attempts: list[int] = []

    async def unreadable(ctx: dict[str, Any]) -> str:
        attempts.append(ctx["job_try"])
        retry_or_fail(ctx, ValidationAppError(code="resume.unreadable_pdf"), task="unreadable")
        return "failed"

    job = await _run(arq_pool, unreadable)
    assert attempts == [1]
    assert await job.result(timeout=5) == "failed"
