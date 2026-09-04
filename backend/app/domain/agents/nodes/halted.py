"""``halted`` -- terminal node for a run that could not finish.

It writes a brief, blameless assistant message explaining the stop, logs a
``warning`` action, and echoes the run's halt status back to the graph.
"""

from typing import TYPE_CHECKING, Any

from app.domain.agents.blocks import TextBlock, dump_blocks
from app.domain.agents.state import ManaState
from app.models.ai import Message

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def halted(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    reason = state.get("error") or "something went wrong"
    text = f"I couldn't finish that — {reason}. You can try again."
    blocks = dump_blocks([TextBlock(markdown=text)])

    deps.session.add(
        Message(
            ai_session_id=deps.session_id,
            user_id=deps.user_id,
            role="assistant",
            content=text,
            blocks=blocks,
            model_id="fake",
            provider="fake",
        )
    )
    await deps.session.flush()

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="halted",
        action_key="halted",
        summary=reason,
        status="warning",
    )

    return {
        "blocks": blocks,
        "status": state.get("status", "halted"),
        "_summary": f"Halted: {reason}",
    }
