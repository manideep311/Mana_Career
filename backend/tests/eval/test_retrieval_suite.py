from eval.suites.retrieval import load_golden, run_retrieval_suite


def test_golden_set_is_well_formed():
    cases = load_golden()
    assert len(cases) >= 15
    for c in cases:
        assert c["source"] == "job_chunks"
        assert c["query"].strip()
        assert isinstance(c["relevant"], list) and c["relevant"]
        for ref in c["relevant"]:
            key, sep, idx = ref.partition(":")
            assert key and sep == ":" and idx.isdigit()


async def test_suite_runs_and_clears_ci_thresholds_on_fake(db_session):
    report = await run_retrieval_suite(
        db_session, provider="fake", write_db=False, git_sha="test",
    )
    assert report.aggregate["recall_at_10"] >= 0.75
    assert report.aggregate["mrr"] >= 0.45
    assert report.aggregate["ndcg_at_10"] >= 0.55
    assert report.passed is True
    assert len(report.cases) == len(load_golden())


async def test_suite_write_db_persists_a_run(db_session):
    from sqlalchemy import select

    from app.models.eval import EvalResult, EvalRun

    report = await run_retrieval_suite(
        db_session, provider="fake", write_db=True, git_sha="deadbeef",
    )
    run = (await db_session.execute(select(EvalRun))).scalars().one()
    assert run.suite == "retrieval" and run.git_sha == "deadbeef"
    results = (
        await db_session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == run.id)
        )
    ).scalars().all()
    assert len(results) == len(report.cases)
