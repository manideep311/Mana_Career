from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import Budget, StepEvent

if TYPE_CHECKING:
    from app.domain.agents.state import ManaState

DEFAULT_MAX_STEPS = 24
DEFAULT_MAX_LLM_CALLS = 12
DEFAULT_TOOL_CAPS: dict[str, int] = {"web_search": 4, "vector_search": 6}
DEFAULT_DEADLINE_SECONDS = 180
DEFAULT_MAX_COST_USD = 0.75


class BudgetExceeded(Exception):
    """Raised by :func:`check_budget` when a guardrail dimension is exhausted."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def new_budget(*, now: float) -> Budget:
    """Build a fresh :class:`Budget` seeded from the module defaults."""
    return Budget(
        max_steps=DEFAULT_MAX_STEPS,
        steps_taken=0,
        max_llm_calls=DEFAULT_MAX_LLM_CALLS,
        llm_calls_made=0,
        tool_call_caps=dict(DEFAULT_TOOL_CAPS),
        tool_calls_made={key: 0 for key in DEFAULT_TOOL_CAPS},
        deadline_ts=now + DEFAULT_DEADLINE_SECONDS,
        max_cost_usd=DEFAULT_MAX_COST_USD,
        cost_usd=0.0,
    )


def check_budget(budget: Budget, *, now: float, tool: str | None = None) -> None:
    """Raise :class:`BudgetExceeded` when any guardrail dimension is exhausted.

    Dimensions are checked in a fixed order: steps, deadline, cost, llm, then the
    per-tool cap (only when ``tool`` is supplied and capped).
    """
    if budget["steps_taken"] >= budget["max_steps"]:
        raise BudgetExceeded("steps")
    if now >= budget["deadline_ts"]:
        raise BudgetExceeded("deadline")
    if budget["cost_usd"] >= budget["max_cost_usd"]:
        raise BudgetExceeded("cost")
    if budget["llm_calls_made"] >= budget["max_llm_calls"]:
        raise BudgetExceeded("llm")
    if (
        tool is not None
        and tool in budget["tool_call_caps"]
        and budget["tool_calls_made"].get(tool, 0) >= budget["tool_call_caps"][tool]
    ):
        raise BudgetExceeded(f"tool:{tool}")


NodeFn = Callable[["ManaState"], Awaitable[dict[str, Any]]]


def guard(node_name: str, fn: NodeFn) -> NodeFn:
    """Wrap a graph node so stop requests and budget breaches become terminal state.

    The wrapper: (1) short-circuits to ``halted`` on ``stop_requested``; (2) runs
    ``check_budget`` and halts on breach; (3) catches any node exception as
    ``error``; (4) builds an ``ok`` :class:`StepEvent`; (5) shallow-copies the
    budget with ``steps_taken`` bumped; (6) returns the node's partial with
    underscored keys stripped, plus ``budget`` and ``step_log``.
    """

    async def wrapper(state: ManaState) -> dict[str, Any]:
        if state.get("stop_requested"):
            stopped: StepEvent = {
                "step_index": len(state.get("step_log", [])),
                "node": node_name,
                "status": "budget_exceeded",
                "summary": "stopped",
                "detail": {},
                "llm_calls": state.get("budget", {}).get("llm_calls_made", 0),
                "cost_usd": state.get("budget", {}).get("cost_usd", 0.0),
                "duration_ms": 0,
            }
            return {"status": "halted", "error": "stopped", "step_log": [stopped]}

        t0 = time.time()
        try:
            check_budget(state["budget"], now=t0)
        except BudgetExceeded as e:
            breached: StepEvent = {
                "step_index": len(state.get("step_log", [])),
                "node": node_name,
                "status": "budget_exceeded",
                "summary": f"budget: {e.reason}",
                "detail": {},
                "llm_calls": state["budget"]["llm_calls_made"],
                "cost_usd": state["budget"]["cost_usd"],
                "duration_ms": 0,
            }
            return {"status": "halted", "error": e.reason, "step_log": [breached]}

        try:
            partial = await fn(state)
        except Exception as exc:
            failed: StepEvent = {
                "step_index": len(state.get("step_log", [])),
                "node": node_name,
                "status": "error",
                "summary": str(exc)[:200],
                "detail": {},
                "llm_calls": state["budget"]["llm_calls_made"],
                "cost_usd": state["budget"]["cost_usd"],
                "duration_ms": int((time.time() - t0) * 1000),
            }
            return {"status": "error", "error": str(exc), "step_log": [failed]}

        event: StepEvent = {
            "step_index": len(state.get("step_log", [])),
            "node": node_name,
            "status": partial.get("_step_status", "ok"),
            "summary": partial.get("_summary", node_name),
            "detail": partial.get("_detail", {}),
            "llm_calls": state["budget"]["llm_calls_made"],
            "cost_usd": state["budget"]["cost_usd"],
            "duration_ms": int((time.time() - t0) * 1000),
        }
        updated = state["budget"].copy()
        updated["steps_taken"] += 1
        return {
            **{k: v for k, v in partial.items() if not k.startswith("_")},
            "budget": updated,
            "step_log": [event],
        }

    return wrapper


def budget_now() -> float:
    """Return wall-clock time; a seam tests can monkeypatch."""
    return time.time()
