from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.ai import RunRefOut
from app.api.v1.schemas.applications import (
    ApplicationCreateIn,
    ApplicationListOut,
    ApplicationOut,
    ApplicationPatchIn,
)
from app.core.audit import audit
from app.domain.agents.service import AgentService
from app.domain.applications.service import ApplicationService
from app.models.application import Application
from app.models.application_event import ApplicationEvent

router = APIRouter(prefix="/applications", tags=["applications"])


def _application_out(a: Application) -> ApplicationOut:
    return ApplicationOut(
        id=a.id, job_id=a.job_id, resume_version_id=a.resume_version_id,
        cover_letter_id=a.cover_letter_id, application_email_id=a.application_email_id,
        status=a.status, match_score=a.match_score, source=a.source,
        applied_at=a.applied_at, last_status_change_at=a.last_status_change_at,
        notes=a.notes, ai_session_id=a.ai_session_id,
        created_at=a.created_at, updated_at=a.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_application(
    body: ApplicationCreateIn, db: DbDep, user: CurrentUser, response: Response
) -> RunRefOut | ApplicationOut:
    if body.intent == "save":
        app_row = Application(
            user_id=user.id, job_id=body.job_id, status="saved", source="user",
        )
        db.add(app_row)
        await db.flush()
        db.add(
            ApplicationEvent(
                application_id=app_row.id, user_id=user.id, kind="status_change",
                from_status=None, to_status="saved",
            )
        )
        await audit(
            db, actor_type="user", action="application.saved",
            actor_user_id=user.id, resource_type="application", resource_id=app_row.id,
        )
        await db.commit()
        response.status_code = status.HTTP_201_CREATED
        return _application_out(app_row)

    session = await AgentService(db).create_session(user.id, kind="agent_run")
    run_id = await AgentService(db).start_run(
        user.id, session.id, goal="prepare_application",
        inputs={"job_id": str(body.job_id)},
    )
    await db.commit()
    return RunRefOut(run_id=run_id, session_id=str(session.id))


@router.get("")
async def list_applications(
    db: DbDep,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = "recent",
    limit: int = 100,
    offset: int = 0,
) -> ApplicationListOut:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows, total = await ApplicationService(db).list_(
        user.id, status=status_filter, sort=sort, limit=limit, offset=offset,
    )
    return ApplicationListOut(
        items=[_application_out(r) for r in rows], total=total, limit=limit, offset=offset,
    )


@router.get("/{application_id}")
async def get_application(
    application_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ApplicationOut:
    return _application_out(await ApplicationService(db).get(user.id, application_id))


@router.patch("/{application_id}")
async def patch_application(
    application_id: uuid.UUID, body: ApplicationPatchIn, db: DbDep, user: CurrentUser
) -> ApplicationOut:
    row = await ApplicationService(db).patch(
        user.id, application_id, status=body.status, notes=body.notes,
    )
    return _application_out(row)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> None:
    await ApplicationService(db).soft_delete(user.id, application_id)
