from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.profile import (
    SUBENTITY_SCHEMAS,
    CareerProfileOut,
    ProfileFullOut,
    ReorderIn,
    StrengthOut,
)
from app.api.v1.schemas.profile import CareerProfileUpdate as _Update
from app.domain.profile.service import ProfileService
from app.domain.profile.strength import ProfileCounts, compute_strength

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
async def get_profile(db: DbDep, user: CurrentUser) -> ProfileFullOut:
    profile, sections = await ProfileService(db).load_full(user.id)
    return ProfileFullOut(
        **CareerProfileOut.model_validate(profile).model_dump(),
        **sections,
    )


@router.put("")
async def update_profile(body: _Update, db: DbDep, user: CurrentUser) -> CareerProfileOut:
    profile = await ProfileService(db).update_scalars(
        user.id, body.model_dump(exclude_unset=True)
    )
    return CareerProfileOut.model_validate(profile)


@router.get("/strength")
async def get_strength(db: DbDep, user: CurrentUser) -> StrengthOut:
    profile, sections = await ProfileService(db).load_full(user.id)
    counts = ProfileCounts(
        experiences=len(sections["experiences"]),
        education=len(sections["education"]),
        projects=len(sections["projects"]),
        certifications=len(sections["certifications"]),
    )
    result = compute_strength(profile, counts)
    return StrengthOut(
        score=result.score, completeness=result.completeness, missing=result.missing
    )


def _make_subentity_router(section: str) -> APIRouter:
    _in, out, patch = SUBENTITY_SCHEMAS[section]
    r = APIRouter(prefix=f"/{section}", tags=["profile"])

    async def list_items(db: DbDep, user: CurrentUser) -> Any:
        return await ProfileService(db).list_section(user.id, section)

    async def create_item(payload: BaseModel, db: DbDep, user: CurrentUser) -> Any:
        return await ProfileService(db).add_item(
            user.id, section, payload.model_dump(exclude_unset=True)
        )

    async def patch_item(
        item_id: uuid.UUID, payload: BaseModel, db: DbDep, user: CurrentUser
    ) -> Any:
        return await ProfileService(db).update_item(
            user.id, section, item_id, payload.model_dump(exclude_unset=True)
        )

    async def delete_item(item_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
        await ProfileService(db).delete_item(user.id, section, item_id)

    async def reorder(payload: ReorderIn, db: DbDep, user: CurrentUser) -> Any:
        return await ProfileService(db).reorder(user.id, section, payload.ids)

    # FastAPI reads the real class off __annotations__; mypy sees BaseModel.
    create_item.__annotations__["payload"] = _in
    patch_item.__annotations__["payload"] = patch

    list_of_out: Any = list.__class_getitem__(out)  # runtime list[<Out>]
    r.add_api_route("", list_items, methods=["GET"], response_model=list_of_out)
    r.add_api_route("", create_item, methods=["POST"], status_code=201, response_model=out)
    r.add_api_route("/reorder", reorder, methods=["POST"], response_model=list_of_out)
    r.add_api_route("/{item_id}", patch_item, methods=["PATCH"], response_model=out)
    r.add_api_route("/{item_id}", delete_item, methods=["DELETE"], status_code=204)
    return r


for _section in SUBENTITY_SCHEMAS:
    router.include_router(_make_subentity_router(_section))
