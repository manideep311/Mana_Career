"""The person's own account: take a copy of their data, or delete it all."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.cookies import clear_refresh_cookie
from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.core.audit import audit
from app.domain.account.deletion import AccountDeleter
from app.domain.account.export import AccountExporter
from app.infra.storage.factory import get_file_store

router = APIRouter(prefix="/account", tags=["account"])


class DeleteAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=200)
    # Typed by the person in the dialog; guards against a stray request.
    confirm: Literal["DELETE"]


@router.get("/export")
async def export_account(db: DbDep, user: CurrentUser, settings: SettingsDep) -> Response:
    filename, blob = await AccountExporter(db, get_file_store(settings)).export(user)
    await audit(
        db, actor_type="user", action="account.exported", actor_user_id=user.id,
        resource_type="user", resource_id=user.id, meta={"bytes": len(blob)},
    )
    return Response(
        content=blob,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountIn, response: Response, db: DbDep, user: CurrentUser,
    settings: SettingsDep,
) -> None:
    deleter = AccountDeleter(db, settings, get_file_store(settings))
    plan = await deleter.delete(user, body.password)
    await db.commit()  # files and agent state go only once the account is gone
    await deleter.cleanup(plan)
    clear_refresh_cookie(response, settings)
