from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.skill_gaps import SkillGapOut, SkillGapPatchIn
from app.domain.matching.service import MatchService
from app.models.match import SkillGap

router = APIRouter(prefix="/skill-gaps", tags=["skill-gaps"])


def _gap_out(g: SkillGap) -> SkillGapOut:
    return SkillGapOut(
        id=g.id,
        scope=g.scope,
        job_match_id=g.job_match_id,
        skill_slug=g.skill_slug,
        skill_label=g.skill_label,
        severity=g.severity,
        frequency=g.frequency,
        rationale=g.rationale,
        status=g.status,
    )


@router.get("")
async def list_skill_gaps(
    db: DbDep,
    user: CurrentUser,
    scope: str = "job",
    job_match_id: uuid.UUID | None = None,
) -> list[SkillGapOut]:
    rows = await MatchService(db).list_skill_gaps(
        user.id, scope=scope, job_match_id=job_match_id
    )
    return [_gap_out(g) for g in rows]


@router.patch("/{gap_id}")
async def patch_skill_gap(
    gap_id: uuid.UUID, body: SkillGapPatchIn, db: DbDep, user: CurrentUser
) -> SkillGapOut:
    return _gap_out(await MatchService(db).set_gap_status(user.id, gap_id, body.status))
