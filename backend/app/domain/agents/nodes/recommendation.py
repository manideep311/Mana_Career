"""``recommendation`` -- Phase 7a stub.

The learning / career-roadmap flow lands in a later phase. For now the node is
a no-op that reports itself as a fresh skip so ``guard`` records a clean step.
"""

from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def recommendation(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    return {"_summary": "Roadmap comes later", "_step_status": "skipped_fresh"}
