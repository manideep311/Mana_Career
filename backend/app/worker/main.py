from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.queue import enqueue
from app.worker.tasks import build_profile, extract_resume, parse_resume, ping
from app.worker.tasks.resume import MAX_TRIES

__all__ = ["WorkerSettings", "enqueue"]

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
    functions: ClassVar[list[Any]] = [ping, parse_resume, extract_resume, build_profile]
    redis_settings = _redis_settings()
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    max_jobs = 10
    job_timeout = 300
    max_tries = MAX_TRIES
    retry_jobs = True
    # We never read job results; retaining them would make the _job_id dedup in
    # core.queue reject a legitimate later reprocess of the same résumé.
    keep_result = 0
