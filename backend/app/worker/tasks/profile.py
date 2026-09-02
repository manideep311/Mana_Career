from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.domain.profile.builder import ProfileBuilder
from app.worker.dead_letter import record_failure
from app.worker.tasks.resume import MAX_TRIES

__all__ = ["build_profile"]

log = get_logger("worker.build_profile")


@contextlib.asynccontextmanager
async def _session_for() -> AsyncIterator[AsyncSession]:
    """Session seam for the résumé pipeline.

    Production opens a fresh ``AsyncSessionLocal`` (its own transaction, closed
    on exit). The DB-backed test monkeypatches this to an async-CM that yields
    the shared rolled-back ``db_session`` without closing it, so every
    ``session.commit()`` below just releases/re-opens that session's SAVEPOINT
    (``join_transaction_mode="create_savepoint"``) and the fixture's outer
    ``trans.rollback()`` still discards the whole test's writes.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def build_profile(ctx: dict[str, Any], user_id: str) -> dict[str, Any]:
    async with _session_for() as session:
        try:
            res = await ProfileBuilder(session).rebuild(uuid.UUID(user_id))
            await session.commit()
            log.info(
                "profile_built",
                user_id=user_id,
                matched=res.matched,
                evidence_total=res.evidence_total,
                unmatched=res.unmatched[:20],
            )
            return {
                "user_id": user_id,
                "matched": res.matched,
                "unmatched": len(res.unmatched),
            }
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise  # transient — let ARQ retry, don't dead-letter yet
            await record_failure("build_profile", args=(user_id,), kwargs={}, error=exc)
            raise
