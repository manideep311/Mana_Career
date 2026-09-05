"""``letter_claim_validator`` -- re-run claim validation over the cover letter
``cover_letter`` just wrote, purely to give the trace a discrete step.

Deterministic. Never halts the run. Peer of ``claim_validator`` (résumé) --
see that file's docstring for why this is a separate node rather than one
function parameterized by artifact type: LangGraph node registration is
per-name, and each node's job here is intentionally single-purpose.
"""

import uuid
from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.generation.cover_letter import _collect_sources
from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.tailoring import ClaimValidator, _split_sentences
from app.domain.resume.version_service import TailoringService
from app.models.application import CoverLetter

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def letter_claim_validator(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    letter_id = state.get("cover_letter_id")
    if not letter_id:
        return {"_summary": "Nothing to validate", "_step_status": "skipped_fresh"}

    letter = await deps.session.get(CoverLetter, uuid.UUID(letter_id))
    if letter is None or letter.resume_version_id is None:
        return {"_summary": "Nothing to validate", "_step_status": "skipped_fresh"}

    version = await TailoringService(deps.session).get_version(
        deps.user_id, letter.resume_version_id
    )
    tailored = ResumeExtraction.model_validate(version.content)
    sources = _collect_sources(tailored, "", "")
    report = ClaimValidator(sources).check(_split_sentences(letter.content))

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
        node="letter_claim_validator",
        action_key="validated_letter_claims",
        summary=summary,
        status=status,
    )

    return {"_summary": summary, "_step_status": "ok"}
