from __future__ import annotations

from typing import Any, ClassVar

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.worker.tasks import ping

_settings = get_settings()
log = get_logger("worker")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(_settings.redis_url)


async def _on_startup(ctx: dict[str, Any]) -> None:
    configure_logging(_settings)
    log.info("worker_started")


async def _on_shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker_stopped")


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping]
    redis_settings = _redis_settings()
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    max_jobs = 10
    job_timeout = 300
    max_tries = 3
    retry_jobs = True


async def enqueue(task: str, *args: Any, **kwargs: Any) -> str:
    pool = await create_pool(_redis_settings())
    try:
        job = await pool.enqueue_job(task, *args, **kwargs)
        if job is None:
            raise RuntimeError(f"could not enqueue {task!r} (duplicate job id?)")
        return job.job_id
    finally:
        await pool.aclose()
