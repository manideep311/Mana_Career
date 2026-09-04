"""``match_analysis`` -- for the first five retrieved jobs, get-or-create a
``JobMatch`` and hand the graph a compact ``{job_id, match_id, status}`` ref per
job. Jobs that are missing or not visible to the user are skipped.
"""

import uuid
from typing import TYPE_CHECKING, Any

from app.core.errors import NotFoundError
from app.domain.agents.state import ManaState
from app.domain.matching.service import MatchService

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def match_analysis(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    refs: list[dict[str, str]] = []
    for job_id_str in state.get("retrieved_jobs", [])[:5]:
        try:
            m = await MatchService(deps.session).get_or_create(
                deps.user_id, uuid.UUID(job_id_str)
            )
            refs.append({"job_id": job_id_str, "match_id": str(m.id), "status": m.status})
        except NotFoundError:
            continue

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="match_analysis",
        action_key="lined_up",
        summary=f"Lined up {len(refs)} roles against your profile",
    )

    return {
        "match_refs": refs,
        "_summary": f"Scoring {len(refs)} roles",
        "_detail": {"count": len(refs)},
    }
