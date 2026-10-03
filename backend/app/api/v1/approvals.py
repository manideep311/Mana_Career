from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.api.v1.schemas.approvals import (
    ApprovalDecisionIn,
    ApprovalRequestListOut,
    ApprovalRequestOut,
)
from app.core.errors import ConflictError, NotFoundError
from app.domain.agents.service import AgentService
from app.domain.applications.sending import (
    UNVERIFIED,
    email_confirmation_required,
    set_approval_recipient,
)
from app.models.application import ApprovalRequest

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _approval_out(a: ApprovalRequest) -> ApprovalRequestOut:
    return ApprovalRequestOut(
        id=a.id, application_id=a.application_id, action_type=a.action_type,
        payload_snapshot=dict(a.payload_snapshot), status=a.status,
        decided_at=a.decided_at, decision_note=a.decision_note, created_at=a.created_at,
    )


async def _get_owned(
    db: AsyncSession, user_id: uuid.UUID, approval_id: uuid.UUID
) -> ApprovalRequest:
    row = (
        await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == approval_id, ApprovalRequest.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(detail="Approval not found")
    return row


@router.get("")
async def list_approvals(
    db: DbDep, user: CurrentUser, status: str | None = None
) -> ApprovalRequestListOut:
    # Named `status`, shadowing the `fastapi.status` module import within this
    # function's local scope only -- this function never references
    # `status.HTTP_*` itself (the POST route below does, in its own separate
    # scope), so there is no actual conflict and no alias is needed. FastAPI
    # maps a plain parameter name straight to the same-named query key, so
    # this already serves `GET /approvals?status=pending` correctly.
    stmt = select(ApprovalRequest).where(ApprovalRequest.user_id == user.id)
    if status is not None:
        stmt = stmt.where(ApprovalRequest.status == status)
    rows = (await db.execute(stmt.order_by(ApprovalRequest.created_at.desc()))).scalars().all()
    return ApprovalRequestListOut(items=[_approval_out(r) for r in rows])


@router.get("/{approval_id}")
async def get_approval(
    approval_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ApprovalRequestOut:
    return _approval_out(await _get_owned(db, user.id, approval_id))


@router.post("/{approval_id}", status_code=status.HTTP_202_ACCEPTED)
async def decide_approval(
    approval_id: uuid.UUID, body: ApprovalDecisionIn, db: DbDep, user: CurrentUser,
    settings: SettingsDep,
) -> None:
    approval = await _get_owned(db, user.id, approval_id)
    if approval.status != "pending":
        raise ConflictError("This approval has already been decided.")
    if body.decision == "approve" and email_confirmation_required(user, settings):
        raise ConflictError(UNVERIFIED, code="email_unverified")
    if body.decision == "approve":
        # Refuses if the content changed since review; otherwise records the
        # recipient and re-hashes so the approval covers it.
        await set_approval_recipient(
            db, user_id=user.id, approval=approval, to_email=body.to_email, to_name=body.to_name
        )

    approval.status = "approved" if body.decision == "approve" else "rejected"
    approval.decided_by = user.id
    approval.decided_at = datetime.now(UTC)
    approval.decision_note = body.note
    await db.flush()

    await AgentService(db).resume_run(
        user.id, approval.ai_session_id, decision=body.decision, note=body.note
    )
    await db.commit()
