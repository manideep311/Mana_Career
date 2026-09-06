from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.errors import NotFoundError, ValidationAppError
from app.models.application import Application
from app.models.application_event import ApplicationEvent

_USER_SETTABLE = {"saved", "applied", "interview", "offer", "rejected", "withdrawn"}

_PIPELINE_RANK = case(
    {
        "saved": 0, "preparing": 1, "awaiting_approval": 2, "applied": 3,
        "interview": 4, "offer": 5, "rejected": 6, "withdrawn": 7,
    },
    value=Application.status,
    else_=99,
)


class ApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
        sort: str = "recent",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Application], int]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        where = [Application.user_id == user_id, Application.deleted_at.is_(None)]
        if status is not None:
            where.append(Application.status == status)

        total = (
            await self._session.execute(
                select(func.count()).select_from(Application).where(*where)
            )
        ).scalar_one()

        stmt = select(Application).where(*where)
        if sort == "status":
            stmt = stmt.order_by(_PIPELINE_RANK, Application.updated_at.desc())
        else:
            stmt = stmt.order_by(Application.updated_at.desc())
        rows = (
            await self._session.execute(stmt.limit(limit).offset(offset))
        ).scalars().all()
        return list(rows), int(total)

    async def get(self, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
        row = (
            await self._session.execute(
                select(Application).where(
                    Application.id == application_id,
                    Application.user_id == user_id,
                    Application.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError(detail="Application not found")
        return row

    async def patch(
        self,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
        *,
        status: str | None = None,
        notes: str | None = None,
    ) -> Application:
        app_row = await self.get(user_id, application_id)
        now = datetime.now(UTC)

        if status is not None and status != app_row.status:
            if status not in _USER_SETTABLE:
                raise ValidationAppError(f"Can't set status to {status!r}.")
            from_status = app_row.status
            app_row.status = status
            app_row.last_status_change_at = now
            if status == "applied" and app_row.applied_at is None:
                app_row.applied_at = now
            self._session.add(
                ApplicationEvent(
                    application_id=app_row.id, user_id=user_id, kind="status_change",
                    from_status=from_status, to_status=status,
                )
            )
            await audit(
                self._session,
                actor_type="user",
                action="application.status_change",
                actor_user_id=user_id,
                resource_type="application",
                resource_id=app_row.id,
                meta={"from": from_status, "to": status},
            )

        if notes is not None:
            app_row.notes = notes  # notes=None means "leave unchanged"; send "" to blank

        await self._session.flush()
        return app_row

    async def add_note(
        self, user_id: uuid.UUID, application_id: uuid.UUID, body: str
    ) -> ApplicationEvent:
        await self.get(user_id, application_id)  # ownership + 404
        ev = ApplicationEvent(
            application_id=application_id, user_id=user_id, kind="note", body=body,
        )
        self._session.add(ev)
        await self._session.flush()
        return ev

    async def soft_delete(self, user_id: uuid.UUID, application_id: uuid.UUID) -> None:
        app_row = await self.get(user_id, application_id)
        app_row.deleted_at = datetime.now(UTC)
        await self._session.flush()
