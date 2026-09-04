from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, File, Request, Response, UploadFile, status
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.api.deps import CurrentUser, DbDep, RedisDep, SettingsDep
from app.api.v1.schemas.ai import RunRefOut
from app.api.v1.schemas.resume import (
    ConfirmProfileIn,
    FieldDeltaOut,
    ResumeDiffOut,
    ResumeOut,
    ResumePatchIn,
    ResumeVersionDetailOut,
    ResumeVersionListOut,
    ResumeVersionOut,
    TailorIn,
)
from app.core.db import AsyncSessionLocal
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.events import resume_channel, sse_event, status_stream
from app.domain.agents.service import AgentService
from app.domain.documents.renderer import DocumentRenderer, RenderFormat, RenderUnavailable
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.service import ResumeService
from app.domain.resume.version_service import ResumeDiff, TailoringService
from app.domain.resume.version_service import diff as diff_versions
from app.models.resume_version import ResumeVersion

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _version_out(v: ResumeVersion) -> ResumeVersionOut:
    return ResumeVersionOut(
        id=v.id, kind=v.kind, label=v.label, job_id=v.job_id,
        parent_version_id=v.parent_version_id, created_by=v.created_by,
        created_at=v.created_at,
        claim_validation=v.generation_meta.get("claim_validation", {}),
    )


def _version_detail_out(v: ResumeVersion) -> ResumeVersionDetailOut:
    return ResumeVersionDetailOut(**_version_out(v).model_dump(), content=v.content)


def _diff_out(d: ResumeDiff) -> ResumeDiffOut:
    return ResumeDiffOut(
        deltas=[
            FieldDeltaOut(path=x.path, op=x.op, before=x.before, after=x.after)
            for x in d.deltas
        ]
    )


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
                    yield sse_event({"event": "done", "status": current, "totals": {}})
                    return
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


@router.post("/{resume_id}/tailor", status_code=status.HTTP_202_ACCEPTED)
async def tailor_resume_route(
    resume_id: uuid.UUID, body: TailorIn, db: DbDep, user: CurrentUser
) -> RunRefOut:
    resume = await ResumeService(db).get(user.id, resume_id)
    if resume.confirmed_at is None:
        raise ValidationAppError("Confirm this résumé before tailoring it.")
    session = await AgentService(db).create_session(user.id, kind="agent_run")
    run_id = await AgentService(db).start_run(
        user.id, session.id, goal="tailor_resume",
        inputs={"job_id": str(body.job_id), "resume_id": str(resume_id)},
    )
    await db.commit()
    return RunRefOut(run_id=run_id, session_id=str(session.id))


@router.get("/{resume_id}/versions")
async def list_resume_versions(
    resume_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ResumeVersionListOut:
    versions = await TailoringService(db).list_versions(user.id, resume_id)
    return ResumeVersionListOut(items=[_version_out(v) for v in versions])


@router.get("/versions/{version_id}")
async def get_resume_version(
    version_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ResumeVersionDetailOut:
    version = await TailoringService(db).get_version(user.id, version_id)
    return _version_detail_out(version)


@router.get("/versions/{version_id}/diff")
async def get_resume_version_diff(
    version_id: uuid.UUID, db: DbDep, user: CurrentUser, against: str | None = None
) -> ResumeDiffOut:
    svc = TailoringService(db)
    version = await svc.get_version(user.id, version_id)
    if against and against != "base":
        try:
            against_id = uuid.UUID(against)
        except ValueError as exc:
            raise ValidationAppError("`against` must be a version id or \"base\".") from exc
        base_version = await svc.get_version(user.id, against_id)
    elif version.parent_version_id is not None:
        base_version = await svc.get_version(user.id, version.parent_version_id)
    else:
        base_version = await svc.ensure_base_snapshot(user.id, version.resume_id)
    base_cv = ResumeExtraction.model_validate(base_version.content)
    other_cv = ResumeExtraction.model_validate(version.content)
    return _diff_out(diff_versions(base_cv, other_cv))


@router.get("/versions/{version_id}/render")
async def render_resume_version(
    version_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    fmt: Literal["md", "html", "pdf", "docx"] = "md",
) -> Response:
    version = await TailoringService(db).get_version(user.id, version_id)
    cv = ResumeExtraction.model_validate(version.content)
    try:
        doc = DocumentRenderer().render(cv, RenderFormat(fmt))
    except RenderUnavailable as exc:
        raise ConflictError(str(exc), code="render_unavailable") from exc
    return Response(content=doc.data, media_type=doc.media_type)
