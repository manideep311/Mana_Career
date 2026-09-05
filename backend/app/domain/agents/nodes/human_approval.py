"""``human_approval`` -- pause the graph and wait for a person.

Registered RAW in the graph (never guard()-wrapped) -- see the Phase 10a
spec R1/R2: interrupt() raises GraphInterrupt, which guard()'s bare
except Exception would otherwise catch and mis-report as a node error.

interrupt() re-executes this node's body from the top on resume (R3) --
everything before the interrupt() call must be a harmless repeat. The one
DB read here (re-fetching the ApprovalRequest row) is pure and idempotent;
its result is only used to build the interrupt's payload, and is discarded
on resume in favor of the actual resume value.

No reject-then-revise loop this phase (R8): rejecting is terminal.
"""

import uuid
from typing import TYPE_CHECKING, Any

from langgraph.types import interrupt

from app.domain.agents.state import ManaState
from app.models.application import ApprovalRequest

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def human_approval(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    approval_id = state["approval_request_id"]
    _ = await deps.session.get(ApprovalRequest, uuid.UUID(approval_id))  # harmless re-read

    decision_payload = interrupt({"approval_id": approval_id})

    decision = decision_payload.get("decision") if isinstance(decision_payload, dict) else None
    if decision == "approve":
        return {"approval": decision_payload, "_route": "email_external_action"}
    if decision == "reject":
        return {
            "status": "rejected",
            "approval": decision_payload,
            "_route": "halted",
            "_summary": "You rejected this application",
        }
    return {
        "status": "error",
        "error": "unrecognized approval decision",
        "_route": "halted",
        "_summary": "Something went wrong with your decision",
    }
