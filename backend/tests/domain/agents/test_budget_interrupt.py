import pytest
from langgraph.errors import GraphInterrupt

from app.domain.agents.budget import budget_now, guard, new_budget


async def _raises_interrupt(state):
    raise GraphInterrupt("paused")


async def test_guard_lets_graph_interrupt_propagate():
    wrapped = guard("some_node", _raises_interrupt)
    state = {
        "budget": dict(new_budget(now=budget_now())),
        "step_log": [],
        "stop_requested": False,
    }
    with pytest.raises(GraphInterrupt):
        await wrapped(state)
