from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditLog

log = get_logger("audit")
ActorType = Literal["user", "mana_ai", "system"]


async def audit(
    session: AsyncSession,
    *,
    actor_type: ActorType | str,
    action: str,
    result: Literal["success", "failure"] = "success",
    actor_user_id: uuid.UUID | None = None,
    on_behalf_of_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    row = AuditLog(
        actor_type=actor_type,
        action=action,
        result=result,
        actor_user_id=actor_user_id,
        on_behalf_of_user_id=on_behalf_of_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
        before=before,
        after=after,
        meta=meta,
    )
    try:
        session.add(row)
        await session.flush()
    except asyncio.CancelledError:
        raise
    except Exception:
        # Do NOT rollback here: on the shared request session that would discard
        # the caller's uncommitted work while the route still returns success.
        # Propagate so it becomes an honest 500 instead.
        log.exception("audit_write_failed", action=action)
        raise
