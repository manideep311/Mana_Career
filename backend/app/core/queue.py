from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("queue")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def enqueue(task: str, *args: Any, **kwargs: Any) -> str:
    pool = await create_pool(_redis_settings())
    try:
        job = await pool.enqueue_job(task, *args, **kwargs)
        if job is None:
            # A matching _job_id is already queued/running — dedup did its job.
            log.info("enqueue_skipped_duplicate", task=task, args=list(args))
            return ""
        return job.job_id
    finally:
        await pool.aclose()
