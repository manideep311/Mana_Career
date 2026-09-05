from app.domain.agents.nodes.supervisor import supervisor


class _Deps:  # minimal stand-in; supervisor never touches it
    pass


async def test_supervisor_routes_understand_job():
    out = await supervisor({"goal": "understand_job", "inputs": {}}, deps=_Deps())
    assert out["_route"] == "job_retrieval"


async def test_supervisor_halts_unsupported_goals():
    out = await supervisor({"goal": "analyze_profile", "inputs": {}}, deps=_Deps())
    assert out["status"] == "halted" and out["_route"] == "halted"


# DB tests (CI-deferred) — job_retrieval / match_analysis exercised end-to-end in
# test_graph.py + test_agent_task.py against seeded data.
