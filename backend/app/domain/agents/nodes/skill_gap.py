"""``skill_gap`` -- summarise the stored ``SkillGap`` rows for the job matches
that finished scoring, newest / most severe first, capped at six for display.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.domain.agents.state import ManaState
from app.models.match import SkillGap

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def skill_gap(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    ready = [
        r["match_id"] for r in state.get("match_refs", []) if r["status"] == "ready"
    ]
    if not ready:
        return {
            "skill_gap_summary": {"top": [], "counted": 0},
            "_summary": "No scored gaps yet",
        }

    rows = (
        await deps.session.execute(
            select(SkillGap)
            .where(SkillGap.job_match_id.in_([uuid.UUID(x) for x in ready]))
            .order_by(SkillGap.severity)
        )
    ).scalars().all()

    top = [{"skill": g.skill_label, "severity": g.severity} for g in rows[:6]]
    return {
        "skill_gap_summary": {"top": top, "counted": len(rows)},
        "_summary": f"{len(rows)} skill gaps",
    }
