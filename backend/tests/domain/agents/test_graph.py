from app.domain.agents.graph import _halt_or, _route_from_supervisor


def test_route_from_supervisor_reads_route_key():
    assert _route_from_supervisor({"_route": "job_retrieval"}) == "job_retrieval"
    assert _route_from_supervisor({}) == "halted"


def test_halt_or_short_circuits_on_terminal_status():
    nxt = _halt_or("match_analysis")
    assert nxt({"status": "running"}) == "match_analysis"
    assert nxt({"status": "halted"}) == "halted"
    assert nxt({"status": "error"}) == "halted"


# The full understand_job traversal (supervisor -> ... -> respond -> END, blocks in
# the final state) is exercised in test_agent_task.py against a seeded DB + MemorySaver.
