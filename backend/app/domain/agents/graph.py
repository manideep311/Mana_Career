"""``graph.py`` -- assemble the Mana Career LangGraph ``StateGraph``.

``AgentDeps`` is the per-run bag of collaborators every node closes over;
``build_graph`` registers the thirteen nodes, wires the supervisor fan-out and
the linear ``understand_job`` and ``tailor_resume`` chains, and compiles
against the run's checkpointer.

The supervisor and halted nodes are wired **raw** (they never raise and only
emit routing / terminal keys); the eleven worker nodes are wrapped in
:func:`app.domain.agents.budget.guard` so stop requests and budget breaches
become terminal state.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.agents.budget import guard
from app.domain.agents.nodes.claim_validator import claim_validator
from app.domain.agents.nodes.cover_letter import cover_letter
from app.domain.agents.nodes.email_draft import email_draft
from app.domain.agents.nodes.halted import halted
from app.domain.agents.nodes.job_research import job_research
from app.domain.agents.nodes.job_retrieval import job_retrieval
from app.domain.agents.nodes.letter_claim_validator import letter_claim_validator
from app.domain.agents.nodes.match_analysis import match_analysis
from app.domain.agents.nodes.recommendation import recommendation
from app.domain.agents.nodes.respond import respond
from app.domain.agents.nodes.resume_tailoring import resume_tailoring
from app.domain.agents.nodes.skill_gap import skill_gap
from app.domain.agents.nodes.supervisor import supervisor
from app.domain.agents.search.provider import SearchProvider
from app.domain.agents.service import AgentService
from app.domain.agents.state import ManaState
from app.domain.embeddings.provider import EmbeddingsProvider
from app.domain.llm.provider import LLMProvider


@dataclass
class AgentDeps:
    session: AsyncSession
    llm: LLMProvider
    embeddings: EmbeddingsProvider
    search: SearchProvider
    checkpointer: Any
    publish: Callable[[dict[str, Any]], Awaitable[None]]
    svc: AgentService
    user_id: uuid.UUID
    run_id: str
    session_id: uuid.UUID


def _route_from_supervisor(state: ManaState) -> str:
    return state.get("_route", "halted")


def _halt_or(next_node: str) -> Callable[[ManaState], str]:
    return lambda s: "halted" if s.get("status") in {"halted", "error"} else next_node


def _after_resume_claim_check(state: ManaState) -> str:
    if state.get("status") in {"halted", "error"}:
        return "halted"
    return "cover_letter" if state.get("goal") == "prepare_application" else "respond"


def build_graph(deps: AgentDeps) -> Any:
    g = StateGraph(ManaState)
    g.add_node("supervisor", partial(supervisor, deps=deps))
    for name, fn in [
        ("job_research", job_research),
        ("job_retrieval", job_retrieval),
        ("match_analysis", match_analysis),
        ("skill_gap", skill_gap),
        ("recommendation", recommendation),
        ("resume_tailoring", resume_tailoring),
        ("claim_validator", claim_validator),
        ("cover_letter", cover_letter),
        ("letter_claim_validator", letter_claim_validator),
        ("email_draft", email_draft),
        ("respond", respond),
    ]:
        # guard() returns a precisely-typed Callable[[ManaState], Awaitable[...]];
        # langgraph's add_node overloads only bind NodeInputT off a partial/Runnable.
        g.add_node(name, guard(name, partial(fn, deps=deps)))  # type: ignore[call-overload]
    g.add_node("halted", partial(halted, deps=deps))
    g.set_entry_point("supervisor")
    g.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {
            "job_retrieval": "job_retrieval",
            "job_research": "job_research",
            "resume_tailoring": "resume_tailoring",
            "halted": "halted",
        },
    )
    g.add_conditional_edges(
        "job_research",
        _halt_or("job_retrieval"),
        {"job_retrieval": "job_retrieval", "halted": "halted"},
    )
    g.add_conditional_edges(
        "job_retrieval",
        _halt_or("match_analysis"),
        {"match_analysis": "match_analysis", "halted": "halted"},
    )
    g.add_conditional_edges(
        "match_analysis",
        _halt_or("skill_gap"),
        {"skill_gap": "skill_gap", "halted": "halted"},
    )
    g.add_conditional_edges(
        "skill_gap",
        _halt_or("recommendation"),
        {"recommendation": "recommendation", "halted": "halted"},
    )
    g.add_conditional_edges(
        "recommendation",
        _halt_or("respond"),
        {"respond": "respond", "halted": "halted"},
    )
    g.add_conditional_edges(
        "resume_tailoring",
        _halt_or("claim_validator"),
        {"claim_validator": "claim_validator", "halted": "halted"},
    )
    g.add_conditional_edges(
        "claim_validator",
        _after_resume_claim_check,
        {"cover_letter": "cover_letter", "respond": "respond", "halted": "halted"},
    )
    g.add_conditional_edges(
        "cover_letter",
        _halt_or("letter_claim_validator"),
        {"letter_claim_validator": "letter_claim_validator", "halted": "halted"},
    )
    g.add_conditional_edges(
        "letter_claim_validator",
        _halt_or("email_draft"),
        {"email_draft": "email_draft", "halted": "halted"},
    )
    g.add_conditional_edges(
        "email_draft",
        _halt_or("respond"),
        {"respond": "respond", "halted": "halted"},
    )
    g.add_edge("respond", END)
    g.add_edge("halted", END)
    return g.compile(checkpointer=deps.checkpointer)
