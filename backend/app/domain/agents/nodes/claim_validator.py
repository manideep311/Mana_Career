"""``claim_validator`` -- re-run claim validation over the version
``resume_tailoring`` just wrote, purely to give the trace a discrete step.

Deterministic. Never halts the run.
"""

import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.tailoring import ClaimValidator, _collect_sources, _resume_claim_lines
from app.domain.resume.version_service import TailoringService

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def claim_validator(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    version_id = state.get("tailored_resume_version_id")
    if not version_id:
        return {"_summary": "Nothing to validate", "_step_status": "skipped_fresh"}

    version = await TailoringService(deps.session).get_version(
        deps.user_id, uuid.UUID(version_id)
    )
    tailored = ResumeExtraction.model_validate(version.content)
    sources = _collect_sources(tailored, "")
    report = ClaimValidator(sources).check(_resume_claim_lines(tailored))

    if report.passed:
        summary = f"All {report.checked} claims grounded"
        status = "ok"
    else:
        summary = f"{len(report.unsupported)} of {report.checked} claims need a source"
        status = "warning"

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="claim_validator",
        action_key="validated_claims",
        summary=summary,
        status=status,
    )

    return {"_summary": summary, "_step_status": "ok"}
