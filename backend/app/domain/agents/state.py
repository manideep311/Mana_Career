from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

AgentGoal = Literal[
    "understand_job", "enrich_job", "analyze_profile", "prepare_application", "tailor_resume"
]

NODE_ORDER: tuple[str, ...] = (
    "supervisor",
    "job_research",
    "job_retrieval",
    "match_analysis",
    "skill_gap",
    "recommendation",
    "resume_tailoring",
    "claim_validator",
    "respond",
)


class Budget(TypedDict):
    max_steps: int
    steps_taken: int
    max_llm_calls: int
    llm_calls_made: int
    tool_call_caps: dict[str, int]
    tool_calls_made: dict[str, int]
    deadline_ts: float
    max_cost_usd: float
    cost_usd: float


class StepEvent(TypedDict):
    step_index: int
    node: str
    status: Literal["ok", "deduped", "skipped_fresh", "error", "budget_exceeded"]
    summary: str
    detail: dict[str, Any]
    llm_calls: int
    cost_usd: float
    duration_ms: int


class ManaState(TypedDict, total=False):
    run_id: str
    session_id: str
    user_id: str
    goal: AgentGoal
    inputs: dict[str, Any]
    retrieved_jobs: list[str]
    match_refs: list[dict[str, str]]
    skill_gap_summary: dict[str, Any]
    research_notes: list[str]
    blocks: list[dict[str, Any]]
    tailored_resume_version_id: str | None
    cover_letter_id: str | None
    email_draft_id: str | None
    application_id: str | None
    approval: dict[str, Any] | None
    revise_count: int
    budget: Budget
    tool_cache: dict[str, Any]
    step_log: Annotated[list[StepEvent], operator.add]
    stop_requested: bool
    status: Literal["running", "completed", "rejected", "halted", "error"]
    error: str | None
    _route: str
