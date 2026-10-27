"""Expire demo accounts: nothing a visitor uploads is kept past its retention.

With ``DEMO_RETENTION_DAYS`` set, every account older than that is deleted the
same way a person deletes their own (``AccountDeleter``): every row they own,
their résumé files and their agent run state; the audit trail keeps an
``account.expired`` record with nothing personal in it.

It runs hourly rather than nightly because a free host that sleeps when idle
may never be awake at a fixed hour.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.domain.account.deletion import AccountDeleter
from app.infra.storage.factory import get_file_store
from app.models.user import User

log = get_logger("worker.retention")

# Accounts handled per run; a backlog clears over the next runs.
BATCH = 50


@contextlib.asynccontextmanager
async def _session_for() -> AsyncIterator[AsyncSession]:
    """Session seam (DB tests swap in their rolled-back session)."""
    async with AsyncSessionLocal() as session:
        yield session


async def expire_demo_accounts(
    ctx: dict[str, Any], now: dt.datetime | None = None
) -> dict[str, int]:
    settings = get_settings()
    if settings.demo_retention_days <= 0:
        return {"accounts": 0}
    now = now or dt.datetime.now(dt.UTC)
    cutoff = now - dt.timedelta(days=settings.demo_retention_days)
    expired = 0
    async with _session_for() as session:
        users = (
            await session.execute(
                select(User).where(User.created_at < cutoff).order_by(User.created_at).limit(BATCH)
            )
        ).scalars().all()
        deleter = AccountDeleter(session, settings, get_file_store(settings))
        for user in users:
            try:
                plan = await deleter.expire(user)
                await session.commit()
            except Exception:
                await session.rollback()
                log.warning("account_expiry_failed", user_id=str(user.id), exc_info=True)
                continue
            await deleter.cleanup(plan)
            expired += 1
    if expired:
        log.info(
            "demo_accounts_expired", accounts=expired,
            retention_days=settings.demo_retention_days,
        )
    return {"accounts": expired}
