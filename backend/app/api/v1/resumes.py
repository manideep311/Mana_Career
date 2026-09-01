from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile, status
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.api.deps import CurrentUser, DbDep, RedisDep, SettingsDep
from app.api.v1.schemas.resume import ConfirmProfileIn, ResumeOut, ResumePatchIn
from app.core.db import AsyncSessionLocal
from app.core.errors import NotFoundError, ValidationAppError
from app.core.events import resume_channel, sse_event, status_stream
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.service import ResumeService

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(
    request: Request,
    db: DbDep,
    user: CurrentUser,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
) -> ResumeOut:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > settings.resume_max_bytes:
        raise ValidationAppError(code="resume.too_large")
    data = await file.read()
    resume = await ResumeService(db, settings=settings).create(
        user.id,
        filename=file.filename or "resume.pdf",
        data=data,
        declared_content_type=file.content_type or "",
    )
    return ResumeOut.model_validate(resume)


@router.get("")
async def list_resumes(db: DbDep, user: CurrentUser) -> list[ResumeOut]:
    return [ResumeOut.model_validate(r) for r in await ResumeService(db).list_(user.id)]


@router.get("/{resume_id}")
async def get_resume(resume_id: uuid.UUID, db: DbDep, user: CurrentUser) -> ResumeOut:
    return ResumeOut.model_validate(await ResumeService(db).get(user.id, resume_id))


@router.get("/{resume_id}/events")
async def resume_events(
    resume_id: uuid.UUID, user: CurrentUser, redis: RedisDep
) -> EventSourceResponse:
    # Ownership check in a short-lived session (404s non-owners before streaming);
    # the request session is NOT held open for the life of the stream.
    async with AsyncSessionLocal() as session:
        await ResumeService(session).get(user.id, resume_id)
    channel = resume_channel(str(resume_id))

    async def _gen() -> AsyncIterator[ServerSentEvent]:
        async for payload in status_stream(
            redis, channel, terminal={"extracted", "failed"}
        ):
            if payload.get("event") == "open":
                # Read the current status only after the subscription is live so a
                # transition between the read and the subscribe cannot be missed.
                try:
                    async with AsyncSessionLocal() as s:
                        current = (await ResumeService(s).get(user.id, resume_id)).status
                except NotFoundError:
                    return  # deleted mid-stream — close cleanly
                yield sse_event(
                    {
                        "event": "status",
                        "resource": "resume",
                        "id": str(resume_id),
                        "status": current,
                    }
                )
                if current in {"extracted", "failed"}:
                    return  # status_stream's finally cleans up the subscription
                continue
            yield sse_event(payload)

    return EventSourceResponse(_gen())


@router.get("/{resume_id}/extraction")
async def resume_extraction(
    resume_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ResumeExtraction:
    resume = await ResumeService(db).get(user.id, resume_id)
    if resume.status != "extracted" or resume.extraction is None:
        raise NotFoundError(
            detail="This résumé hasn't been extracted yet.", code="resume.not_extracted"
        )
    return ResumeExtraction.model_validate(resume.extraction)


@router.patch("/{resume_id}")
async def patch_resume(
    resume_id: uuid.UUID, body: ResumePatchIn, db: DbDep, user: CurrentUser
) -> ResumeOut:
    resume = await ResumeService(db).update(
        user.id, resume_id, title=body.title, is_primary=body.is_primary
    )
    return ResumeOut.model_validate(resume)


@router.post("/{resume_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_resume(
    resume_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ResumeOut:
    return ResumeOut.model_validate(await ResumeService(db).reprocess(user.id, resume_id))


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
    await ResumeService(db).delete(user.id, resume_id)


@router.post("/{resume_id}/confirm-profile", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_profile(
    resume_id: uuid.UUID, body: ConfirmProfileIn, db: DbDep, user: CurrentUser
) -> None:
    await ResumeService(db).confirm_profile(user.id, resume_id, body.extraction)
