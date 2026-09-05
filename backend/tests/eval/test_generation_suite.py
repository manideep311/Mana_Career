"""Generation eval suite -- DB integration, CI-deferred."""
from __future__ import annotations

from eval.suites.generation import load_golden, run_generation_suite
from sqlalchemy import select

from app.models.eval import EvalResult, EvalRun


async def test_run_generation_suite_persists_a_passed_run_under_fake(db_session):
    report = await run_generation_suite(
        db_session, llm_provider="fake", write_db=True, git_sha="test-sha"
    )
    assert report.passed is True
    assert 0.0 <= report.aggregate["keyword_coverage"] <= 1.0

    run = (
        await db_session.execute(
            select(EvalRun).where(EvalRun.suite == "generation")
        )
    ).scalar_one()
    assert run.status == "passed"

    results = (
        await db_session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == run.id)
        )
    ).scalars().all()
    assert len(results) == len(load_golden())
