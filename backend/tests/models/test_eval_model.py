from sqlalchemy import select

from app.models.eval import EvalResult, EvalRun


async def test_eval_run_and_results_roundtrip(db_session):
    run = EvalRun(
        suite="retrieval", dataset_ref="datasets/retrieval/golden_v1.jsonl",
        dataset_version="v1", git_sha="abc1234", provider="fake",
        metrics={"recall_at_10": 0.8}, status="passed",
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(EvalResult(
        eval_run_id=run.id, case_id="py-backend-kafka", input={"query": "x"},
        expected={"relevant": ["j:0"]}, actual={"retrieved": ["j:0"]},
        scores={"recall_at_10": 1.0}, passed=True,
    ))
    await db_session.flush()
    rows = (await db_session.execute(
        select(EvalResult).where(EvalResult.eval_run_id == run.id)
    )).scalars().all()
    assert len(rows) == 1 and rows[0].passed is True
    assert run.status == "passed" and run.model_ids == {}
