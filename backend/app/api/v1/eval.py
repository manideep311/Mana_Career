from __future__ import annotations

import os
import uuid

from eval.suites.retrieval import run_retrieval_suite
from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.api.deps import CurrentAdmin, DbDep
from app.api.v1.schemas.eval import (
    EvalResultOut,
    EvalRunIn,
    EvalRunListOut,
    EvalRunOut,
)
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models.eval import EvalResult, EvalRun

router = APIRouter(prefix="/eval", tags=["eval"])


def _run_out(run: EvalRun) -> EvalRunOut:
    return EvalRunOut(
        id=run.id,
        suite=run.suite,
        dataset_version=run.dataset_version,
        git_sha=run.git_sha,
        provider=run.provider,
        model_ids=dict(run.model_ids),
        metrics=dict(run.metrics),
        status=run.status,
        started_at=run.started_at,
        ended_at=run.ended_at,
    )


def _result_out(r: EvalResult) -> EvalResultOut:
    return EvalResultOut(
        id=r.id,
        case_id=r.case_id,
        scores=dict(r.scores),
        passed=r.passed,
        expected=dict(r.expected),
        actual=dict(r.actual),
    )


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_eval_run(body: EvalRunIn, db: DbDep, _: CurrentAdmin) -> EvalRunOut:
    # `suite` is a Literal["retrieval"]; only the retrieval suite is wired up.
    git_sha = os.environ.get("GITHUB_SHA", "dev")[:40]
    await run_retrieval_suite(
        db,
        provider=get_settings().embeddings_provider,
        write_db=True,
        git_sha=git_sha,
    )
    # `run_retrieval_suite(write_db=True)` flushes the EvalRun + EvalResult rows;
    # `get_session` commits them when this handler returns (no explicit commit — R9).
    run = (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.suite == "retrieval")
            .order_by(EvalRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one()
    return _run_out(run)


@router.get("/runs")
async def list_eval_runs(
    db: DbDep,
    _: CurrentAdmin,
    suite: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> EvalRunListOut:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    count_stmt = select(func.count()).select_from(EvalRun)
    page_stmt = select(EvalRun).order_by(EvalRun.started_at.desc())
    if suite is not None:
        count_stmt = count_stmt.where(EvalRun.suite == suite)
        page_stmt = page_stmt.where(EvalRun.suite == suite)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        (await db.execute(page_stmt.limit(limit).offset(offset))).scalars().all()
    )
    return EvalRunListOut(items=[_run_out(r) for r in rows], total=total)


@router.get("/runs/{run_id}")
async def get_eval_run(run_id: uuid.UUID, db: DbDep, _: CurrentAdmin) -> EvalRunOut:
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise NotFoundError(detail="Eval run not found")
    return _run_out(run)


@router.get("/runs/{run_id}/results")
async def list_eval_run_results(
    run_id: uuid.UUID, db: DbDep, _: CurrentAdmin
) -> list[EvalResultOut]:
    rows = (
        (
            await db.execute(
                select(EvalResult)
                .where(EvalResult.eval_run_id == run_id)
                .order_by(EvalResult.case_id)
            )
        )
        .scalars()
        .all()
    )
    return [_result_out(r) for r in rows]
