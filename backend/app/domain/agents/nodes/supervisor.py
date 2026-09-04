"""``supervisor`` -- the graph's entry node.

It reads ``state["goal"]`` and picks the next route. Task 13 wires it **raw**
(not ``guard``-wrapped), so it must never raise and only ever returns plain
routing keys (``_route`` / ``_summary``, plus ``status`` / ``error`` on a halt).
"""

from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def supervisor(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    goal = state["goal"]
    if goal == "tailor_resume":
        return {"_route": "resume_tailoring", "_summary": "Routing: tailor a résumé"}
    if goal == "understand_job":
        return {"_route": "job_retrieval", "_summary": "Routing: understand a job"}
    if goal == "enrich_job":
        return {"_route": "job_research", "_summary": "Routing: research a job"}
    return {
        "status": "halted",
        "error": "not available yet",
        "_route": "halted",
        "_summary": "That flow isn't available yet",
    }
