import time

import pytest

from app.domain.agents.budget import BudgetExceeded, new_budget
from app.domain.agents.tools.registry import TOOL_SPECS, call_tool, tool_key


def test_tool_key_is_order_stable():
    assert tool_key("t", {"a": 1, "b": 2}) == tool_key("t", {"b": 2, "a": 1})
    assert tool_key("t", {"a": 1}) != tool_key("t", {"a": 2})


async def test_call_tool_caches_and_dedupes():
    calls = {"n": 0}

    async def fn(**kw):
        calls["n"] += 1
        return {"hits": kw["q"]}

    state = {"budget": new_budget(now=time.time()), "tool_cache": {}}
    r1, d1 = await call_tool(state, TOOL_SPECS["vector_search"], {"q": "x"}, fn)
    r2, d2 = await call_tool(state, TOOL_SPECS["vector_search"], {"q": "x"}, fn)
    assert d1 == "ok" and d2 == "deduped" and r1 == r2 == {"hits": "x"}
    assert calls["n"] == 1
    assert state["budget"]["tool_calls_made"]["vector_search"] == 1  # not double-counted


async def test_call_tool_enforces_the_per_tool_cap():
    async def fn(**kw):
        return 1

    b = new_budget(now=time.time())
    b["tool_calls_made"]["web_search"] = 4
    state = {"budget": b, "tool_cache": {}}
    with pytest.raises(BudgetExceeded):
        await call_tool(state, TOOL_SPECS["web_search"], {"q": "y"}, fn, now=time.time())
