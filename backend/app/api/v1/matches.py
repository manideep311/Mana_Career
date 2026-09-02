from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.matches import (
    MatchComponentOut,
    MatchCreateIn,
    MatchListOut,
    MatchOut,
    MatchRefOut,
    RecomputeIn,
)
from app.domain.matching.service import MatchService
from app.models.match import JobMatch, MatchComponent

router = APIRouter(prefix="/matches", tags=["matches"])


def _match_out(m: JobMatch) -> MatchOut:
    return MatchOut(
        id=m.id,
        job_id=m.job_id,
        status=m.status,
        score=float(m.score) if m.score is not None else None,
        band=m.band,
        dimension_scores={k: float(v) for k, v in m.dimension_scores.items()},
        strengths=list(m.strengths),
        gaps=list(m.gaps),
        explanation=m.explanation,
        computed_at=m.computed_at,
    )


def _component_out(c: MatchComponent) -> MatchComponentOut:
    return MatchComponentOut(
        dimension=c.dimension,
        raw_score=float(c.raw_score),
        weight=float(c.weight),
        contribution=float(c.contribution),
        detail=dict(c.detail),
        evidence=list(c.evidence),
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_match(body: MatchCreateIn, db: DbDep, user: CurrentUser) -> MatchRefOut:
    match = await MatchService(db).get_or_create(user.id, body.job_id)
    return MatchRefOut(id=match.id, status=match.status)


@router.get("")
async def list_matches(
    db: DbDep,
    user: CurrentUser,
    job_id: uuid.UUID | None = None,
    min_score: float | None = None,
    sort: str = "score",
) -> MatchListOut:
    rows = await MatchService(db).list_for_user(
        user.id, job_id=job_id, min_score=min_score, sort=sort
    )
    return MatchListOut(items=[_match_out(m) for m in rows])


@router.post("/recompute", status_code=status.HTTP_202_ACCEPTED)
async def recompute_matches(
    body: RecomputeIn, db: DbDep, user: CurrentUser
) -> dict[str, Any]:
    is_all = body.scope == "all"
    count = await MatchService(db).recompute(
        user.id,
        scope="all" if is_all else "job",
        job_id=None if is_all else uuid.UUID(body.scope),
    )
    return {"status": "queued", "count": count}


@router.get("/{match_id}")
async def get_match(match_id: uuid.UUID, db: DbDep, user: CurrentUser) -> MatchOut:
    return _match_out(await MatchService(db).get(user.id, match_id))


@router.get("/{match_id}/components")
async def match_components(
    match_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> list[MatchComponentOut]:
    rows = await MatchService(db).components(user.id, match_id)
    return [_component_out(c) for c in rows]
