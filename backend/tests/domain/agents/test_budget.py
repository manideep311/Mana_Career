import time

import pytest

from app.domain.agents.budget import (
    BudgetExceeded,
    check_budget,
    guard,
    new_budget,
)


def test_new_budget_defaults():
    b = new_budget(now=1000.0)
    assert b["max_steps"] == 24 and b["steps_taken"] == 0
    assert b["deadline_ts"] == 1000.0 + 180
    assert b["tool_call_caps"] == {"web_search": 4, "vector_search": 6}
    assert b["tool_calls_made"] == {"web_search": 0, "vector_search": 0}
    assert b["cost_usd"] == 0.0


def test_check_budget_raises_on_each_dimension():
    b = new_budget(now=0.0)
    with pytest.raises(BudgetExceeded) as ei:
        check_budget({**b, "steps_taken": 24}, now=1.0)
    assert ei.value.reason == "steps"
    with pytest.raises(BudgetExceeded) as ei:
        check_budget(b, now=b["deadline_ts"] + 1)
    assert ei.value.reason == "deadline"
    with pytest.raises(BudgetExceeded) as ei:
        check_budget({**b, "cost_usd": 1.0}, now=1.0)
    assert ei.value.reason == "cost"
    with pytest.raises(BudgetExceeded) as ei:
        check_budget({**b, "llm_calls_made": 12}, now=1.0)
    assert ei.value.reason == "llm"
    with pytest.raises(BudgetExceeded) as ei:
        check_budget({**b, "tool_calls_made": {"web_search": 4, "vector_search": 0}},
                     now=1.0, tool="web_search")
    assert ei.value.reason == "tool:web_search"


def test_check_budget_passes_when_under_all_caps():
    check_budget(new_budget(now=0.0), now=1.0, tool="web_search")


async def test_guard_appends_ok_step_and_bumps_steps_taken():
    async def node(state):
        return {"retrieved_jobs": ["a"], "_summary": "found 1"}

    wrapped = guard("job_retrieval", node)
    state = {"budget": new_budget(now=time.time()), "step_log": []}
    out = await wrapped(state)
    assert out["retrieved_jobs"] == ["a"]
    assert out["budget"]["steps_taken"] == 1
    assert len(out["step_log"]) == 1
    ev = out["step_log"][0]
    assert ev["node"] == "job_retrieval" and ev["status"] == "ok" and ev["summary"] == "found 1"
    assert "_summary" not in out  # underscored keys are stripped


async def test_guard_routes_to_halted_on_budget_breach():
    async def node(state):
        return {}

    wrapped = guard("job_retrieval", node)
    state = {"budget": {**new_budget(now=time.time()), "steps_taken": 24}, "step_log": []}
    out = await wrapped(state)
    assert out["status"] == "halted" and out["error"] == "steps"
    assert out["step_log"][0]["status"] == "budget_exceeded"


async def test_guard_catches_node_exception_as_error_status():
    async def node(state):
        raise RuntimeError("boom")

    out = await guard("respond", node)({"budget": new_budget(now=time.time()), "step_log": []})
    assert out["status"] == "error" and "boom" in out["error"]


async def test_guard_respects_stop_requested():
    async def node(state):
        return {"x": 1}

    out = await guard("respond", node)(
        {"budget": new_budget(now=time.time()), "step_log": [], "stop_requested": True}
    )
    assert out["status"] == "halted" and out["error"] == "stopped"
