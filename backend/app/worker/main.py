from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.queue import enqueue
from app.domain.agents.checkpointer import ensure_checkpointer_tables
from app.worker.retry import MAX_TRIES
from app.worker.tasks import (
    build_profile,
    extract_resume,
    ingest_job,
    parse_resume,
    ping,
    plan_roadmap,
    resume_agent,
    run_agent,
    score_match,
    sweep_stuck_jobs,
)

__all__ = ["WorkerSettings", "enqueue"]

_settings = get_settings()
log = get_logger("worker")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(_settings.redis_url)


async def _on_startup(ctx: dict[str, Any]) -> None:
    configure_logging(_settings)
    await ensure_checkpointer_tables(_settings)
    log.info("worker_started")


async def _on_shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker_stopped")


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        ping,
        parse_resume,
        extract_resume,
        build_profile,
        ingest_job,
        score_match,
        run_agent,
        resume_agent,
        plan_roadmap,
    ]
    redis_settings = _redis_settings()
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    # Every 5 minutes, fail anything left in progress past its deadline.
    cron_jobs: ClassVar[list[Any]] = [
        cron(sweep_stuck_jobs, minute=set(range(0, 60, 5)), unique=True, timeout=120)
    ]
    max_jobs = 10
    job_timeout = 300
    max_tries = MAX_TRIES
    # Tasks raise arq.worker.Retry on transient errors (app.worker.retry).
    retry_jobs = True
    # Heartbeat key for `arq --check` (the compose worker healthcheck).
    health_check_interval = 30
    # We never read job results; retaining them would make the _job_id dedup in
    # core.queue reject a legitimate later reprocess of the same résumé.
    keep_result = 0
