"""Delete an account so that nothing of the person remains.

The database does most of it: every user-owned table cascades from ``users``.
Three things live outside that cascade and are handled here:

- résumé PDFs on disk (``Resume.file_ref``);
- the agent's saved run state (LangGraph checkpoints, one thread per run id);
- audit log rows, which are kept as the security record but lose the IP,
  browser and before/after snapshots.

``delete`` does all database work inside the caller's transaction and returns
a ``CleanupPlan``; the caller commits, then runs ``cleanup`` so no file or
checkpoint is removed for an account that turned out not to be deleted.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import Settings
from app.core.errors import ForbiddenError
from app.core.logging import get_logger
from app.domain.agents.checkpointer import get_checkpointer
from app.domain.auth.passwords import verify_password
from app.infra.storage.base import FileStore
from app.models.ai import AgentStep, AiAction, AiSession
from app.models.application import ApprovalRequest
from app.models.audit import AuditLog
from app.models.resume import Resume
from app.models.user import User

log = get_logger("account.deletion")

CheckpointerFactory = Callable[[Settings], Awaitable[Any]]


@dataclass(frozen=True)
class CleanupPlan:
    user_id: uuid.UUID
    file_refs: tuple[str, ...]
    run_ids: tuple[str, ...]


class AccountDeleter:
    def __init__(
        self, session: AsyncSession, settings: Settings, store: FileStore,
        checkpointer: CheckpointerFactory = get_checkpointer,
    ) -> None:
        self._s = session
        self._settings = settings
        self._store = store
        self._checkpointer = checkpointer

    async def _run_ids(self, uid: uuid.UUID) -> set[str]:
        ids: set[str] = set()
        for stmt in (
            select(AiSession.run_id).where(AiSession.user_id == uid),
            select(AiAction.run_id).where(AiAction.user_id == uid),
            select(ApprovalRequest.run_id).where(ApprovalRequest.user_id == uid),
            select(AgentStep.run_id)
            .join(AiSession, AiSession.id == AgentStep.ai_session_id)
            .where(AiSession.user_id == uid),
        ):
            ids.update(r for (r,) in (await self._s.execute(stmt)).all() if r)
        return ids

    async def delete(self, user: User, password: str) -> CleanupPlan:
        """Remove the account (not committed). Raises on a wrong password."""
        if not verify_password(user.password_hash, password):
            # 403, not 401: a typo must not look like an expired session.
            raise ForbiddenError(detail="That password isn't right.", code="invalid_password")
        uid = user.id
        file_refs = tuple(
            r for (r,) in (
                await self._s.execute(select(Resume.file_ref).where(Resume.user_id == uid))
            ).all()
        )
        run_ids = tuple(sorted(await self._run_ids(uid)))

        await self._s.execute(
            update(AuditLog)
            .where(or_(AuditLog.actor_user_id == uid, AuditLog.on_behalf_of_user_id == uid))
            .values(ip=None, user_agent=None, before=None, after=None)
        )
        # The record that an account was deleted, with nothing personal in it.
        await audit(
            self._s, actor_type="user", action="account.deleted", actor_user_id=uid,
            resource_type="user", resource_id=uid,
            meta={"resumes": len(file_refs), "agent_runs": len(run_ids)},
        )
        await self._s.delete(user)  # every user-owned table cascades from here
        await self._s.flush()
        return CleanupPlan(user_id=uid, file_refs=file_refs, run_ids=run_ids)

    async def cleanup(self, plan: CleanupPlan) -> None:
        """After commit: remove files and agent run state. Best effort, logged."""
        if plan.run_ids:
            saver = await self._checkpointer(self._settings)
            for run_id in plan.run_ids:
                try:
                    await saver.adelete_thread(run_id)
                except Exception:
                    log.warning("account_checkpoint_delete_failed", run_id=run_id)
        for ref in plan.file_refs:
            try:
                await self._store.delete(ref)
            except Exception:
                log.warning("account_file_delete_failed", file_ref=ref)
        log.info(
            "account_deleted", user_id=str(plan.user_id), files=len(plan.file_refs),
            agent_runs=len(plan.run_ids),
        )
