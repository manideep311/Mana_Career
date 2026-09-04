from app.domain.agents.nodes.supervisor import supervisor


async def test_supervisor_routes_tailor_resume():
    out = await supervisor({"goal": "tailor_resume", "inputs": {"job_id": "j1"}}, deps=object())
    assert out["_route"] == "resume_tailoring"


async def test_supervisor_still_halts_unknown_goals():
    out = await supervisor({"goal": "analyze_profile", "inputs": {}}, deps=object())
    assert out["_route"] == "halted"
