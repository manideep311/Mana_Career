from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.ai import RunRefOut
from app.api.v1.schemas.applications import ApplicationCreateIn, ApplicationOut
from app.core.errors import NotFoundError
from app.domain.agents.service import AgentService
from app.models.application import Application

router = APIRouter(prefix="/applications", tags=["applications"])


def _application_out(a: Application) -> ApplicationOut:
    return ApplicationOut(
        id=a.id, job_id=a.job_id, resume_version_id=a.resume_version_id,
        cover_letter_id=a.cover_letter_id, application_email_id=a.application_email_id,
        status=a.status, match_score=a.match_score, source=a.source,
        applied_at=a.applied_at, last_status_change_at=a.last_status_change_at,
        created_at=a.created_at, updated_at=a.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_application(
    body: ApplicationCreateIn, db: DbDep, user: CurrentUser
) -> RunRefOut:
    session = await AgentService(db).create_session(user.id, kind="agent_run")
    run_id = await AgentService(db).start_run(
        user.id, session.id, goal="prepare_application",
        inputs={"job_id": str(body.job_id)},
    )
    await db.commit()
    return RunRefOut(run_id=run_id, session_id=str(session.id))


@router.get("/{application_id}")
async def get_application(
    application_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ApplicationOut:
    row = (
        await db.execute(
            select(Application).where(
                Application.id == application_id, Application.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(detail="Application not found")
    return _application_out(row)
