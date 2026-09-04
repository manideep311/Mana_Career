"""``respond`` -- the terminal node for the read-only flows.

It turns whatever the graph gathered into an assistant message: a short plain
answer plus one ``JobCardBlock`` per lined-up role, or an
``InsufficientInfoBlock`` when there was nothing in the corpus to compare
against. The message is persisted, an action is logged, and the run is marked
``completed``.
"""

import uuid
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.domain.agents.blocks import (
    InsufficientInfoBlock,
    JobCardBlock,
    TextBlock,
    dump_blocks,
)
from app.domain.agents.state import ManaState
from app.models.ai import Message

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps

_RESPOND_SYSTEM = (
    "You are Mana, a career assistant. Answer plainly in 2-3 sentences. "
    "Never invent facts about a job or about the user, and never state a "
    "numeric match score. Point the user at the job cards below for the "
    "detailed breakdown."
)


def _fallback_text(n: int) -> str:
    if n == 0:
        return (
            "I pulled together what I could from your job corpus — open a role "
            "to see how it lines up."
        )
    return (
        f"Here are {n} roles that line up with your background — open one to "
        "see the match breakdown."
    )


def _respond_prompt(state: ManaState) -> str:
    retrieved = len(state.get("retrieved_jobs", []))
    gaps = state.get("skill_gap_summary", {})
    return (
        f"I retrieved {retrieved} candidate role(s) for the user. "
        f"Skill-gap summary: {gaps}. "
        "Write a short, plain answer that orients them to the job cards below "
        "without repeating the raw numbers."
    )


async def respond(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    match_refs = state.get("match_refs", [])
    n = len(match_refs)

    blocks: list[BaseModel]
    if not state.get("retrieved_jobs"):
        blocks = [
            InsufficientInfoBlock(
                topic="job_match",
                missing=[
                    "a job in your corpus that matches",
                    "a fuller career profile",
                ],
            )
        ]
        text = (
            "I couldn't find roles to compare against your profile yet. "
            "Add or import a few jobs, then ask again."
        )
    else:
        try:
            res = await deps.llm.complete(
                [
                    {"role": "system", "content": _RESPOND_SYSTEM},
                    {"role": "user", "content": _respond_prompt(state)},
                ],
                max_tokens=256,
            )
            state["budget"]["llm_calls_made"] = (
                state["budget"].get("llm_calls_made", 0) + 1
            )
            state["budget"]["cost_usd"] = (
                state["budget"].get("cost_usd", 0.0) + res.cost_usd
            )
            text = (res.text or "").strip() or _fallback_text(n)
        except Exception:
            text = _fallback_text(n)
        blocks = [TextBlock(markdown=text)]
        blocks.extend(
            JobCardBlock(
                job_id=uuid.UUID(r["job_id"]),
                match_id=uuid.UUID(r["match_id"]) if r["match_id"] else None,
            )
            for r in match_refs
        )

    deps.session.add(
        Message(
            ai_session_id=deps.session_id,
            user_id=deps.user_id,
            role="assistant",
            content=text,
            blocks=dump_blocks(blocks),
            model_id=getattr(deps.llm, "model", None) or "fake",
            provider="fake",
        )
    )
    await deps.session.flush()

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="respond",
        action_key="responded",
        summary=f"Answered with {len(blocks)} block(s)",
    )

    return {
        "blocks": dump_blocks(blocks),
        "status": "completed",
        "_summary": "Responded",
    }
