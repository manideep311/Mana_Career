"""``email_external_action`` -- the graph's only side effect: send the approved email.

All the rules (approval still ``approved``, content still matching the reviewed
hash, at-most-once delivery, redirect vs live, daily caps, résumé attachment)
live in ``app.domain.applications.sending`` so the "Try sending again" endpoint
follows exactly the same path.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.applications.sending import send_approved_application
from app.models.application import ApprovalRequest

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def email_external_action(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    approval = await deps.session.get(ApprovalRequest, uuid.UUID(state["approval_request_id"]))
    if approval is None or approval.status != "approved":
        return {
            "status": "halted",
            "error": "approval not in an approved state",
            "_summary": "This application hasn't been approved",
        }

    outcome = await send_approved_application(
        deps.session, user_id=deps.user_id, approval=approval,
        sender=deps.email_sender, settings=deps.settings,
    )
    if outcome.status != "sent":
        return {"status": "halted", "error": outcome.message, "_summary": outcome.message}

    now = datetime.now(UTC)
    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="email_external_action",
        action_key="sent_application_email",
        # `%-I` (strip the leading zero from the 12-hour hour) is glibc-only;
        # `.lstrip("0")` is the portable equivalent -- 12-hour format never
        # yields "00", so it only ever drops a genuine leading zero.
        summary=f"Application sent at {now.strftime('%I:%M %p').lstrip('0')}",
        entity_type="application",
        entity_id=approval.application_id,
    )
    return {"status": "completed", "_summary": outcome.message}
