import operator

from app.domain.agents.state import NODE_ORDER, Budget, ManaState, StepEvent


def test_manastate_is_total_false_and_has_route_key():
    assert ManaState.__total__ is False
    assert "run_id" in ManaState.__annotations__
    assert "_route" in ManaState.__annotations__
    assert "step_log" in ManaState.__annotations__


def test_step_log_uses_operator_add_reducer():
    from typing import get_args, get_type_hints

    hints = get_type_hints(ManaState, include_extras=True)
    step_log = hints["step_log"]
    assert operator.add in get_args(step_log)


def test_node_order_starts_at_supervisor_ends_at_respond():
    assert NODE_ORDER[0] == "supervisor" and NODE_ORDER[-1] == "respond"


def test_budget_and_stepevent_shapes():
    assert set(Budget.__annotations__) >= {
        "max_steps", "steps_taken", "deadline_ts", "max_cost_usd", "cost_usd",
        "tool_call_caps", "tool_calls_made",
    }
    assert set(StepEvent.__annotations__) >= {
        "step_index", "node", "status", "summary", "llm_calls", "cost_usd", "duration_ms",
    }
