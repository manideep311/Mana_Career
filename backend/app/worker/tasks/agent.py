"""``run_agent``/``resume_agent`` -- the ARQ worker tasks that drive a Mana
Career LangGraph run.

``run_agent`` starts a fresh run; ``resume_agent`` resumes one paused at a
``human_approval`` interrupt (Command(resume=...) instead of a fresh init --
see the Phase 10a spec R5/R6). Both share ``_drive()``, which streams the
compiled graph with ``stream_mode="updates"``, persists every StepEvent the
guard emits and republishes it (plus response blocks) to the run's SSE
channel, then either finalizes the session (the graph reached a terminal
state) or marks it ``awaiting_approval`` (the graph paused at a new
interrupt) by reading ``graph.aget_state(...).interrupts``. The
``except``/``finally`` block in each entry point follows the repo's F3
retry discipline: transient tries re-raise untouched; the terminal try
finalizes the session as ``error``, publishes a generic failure, and
records a dead-letter entry.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from langgraph.types import Command
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.domain.agents.checkpointer import get_checkpointer
from app.domain.agents.graph import AgentDeps, build_graph
from app.domain.agents.search.factory import get_search_provider
from app.domain.agents.service import AgentService
from app.domain.agents.state import ManaState
from app.domain.email.factory import get_email_sender
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.llm.factory import get_llm_provider
from app.models.ai import AiSession
from app.worker.dead_letter import record_failure
from app.worker.tasks.resume import MAX_TRIES

__all__ = ["resume_agent", "run_agent"]

log = get_logger("worker.run_agent")


@contextlib.asynccontextmanager
async def _session_for() -> AsyncIterator[AsyncSession]:
    """Session seam for the résumé pipeline.

    Production opens a fresh ``AsyncSessionLocal`` (its own transaction, closed
    on exit). The DB-backed test monkeypatches this to an async-CM that yields
    the shared rolled-back ``db_session`` without closing it, so every
    ``session.commit()`` below just releases/re-opens that session's SAVEPOINT
    (``join_transaction_mode="create_savepoint"``) and the fixture's outer
    ``trans.rollback()`` still discards the whole test's writes.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def _drive(
    *, session: AsyncSession, s: AiSession, run_id: str, graph_input: Any,
    settings: Any, publish: Any,
) -> dict[str, Any]:
    svc = AgentService(session, settings=settings)
    deps = AgentDeps(
        session=session,
        llm=get_llm_provider(settings),
        embeddings=get_embeddings_provider(settings),
        search=get_search_provider(settings),
        checkpointer=await get_checkpointer(settings),
        publish=publish,
        svc=svc,
        email_sender=get_email_sender(settings),
        user_id=s.user_id,
        run_id=run_id,
        session_id=s.id,
    )
    graph = build_graph(deps)
    gcfg = {"configurable": {"thread_id": run_id}}
    await publish({"event": "open", "run_id": run_id})
    async for update in graph.astream(graph_input, config=gcfg, stream_mode="updates"):
        for _node_name, partial_state in update.items():
            if not isinstance(partial_state, dict):
                continue
            for ev in partial_state.get("step_log", []):
                await svc._write_step(session_id=s.id, run_id=run_id, step=ev)
                await publish(
                    {
                        "event": "step",
                        "node": ev["node"],
                        "status": ev["status"],
                        "summary": ev["summary"],
                    }
                )
            for b in partial_state.get("blocks", []):
                await publish({"event": "block", "block": b})

    snap = await graph.aget_state(gcfg)
    if snap.interrupts:
        await svc.mark_awaiting_approval(s.id)
        await session.commit()
        interrupt_value = snap.interrupts[0].value
        approval_id = (
            interrupt_value.get("approval_id")
            if isinstance(interrupt_value, dict)
            else None
        )
        await publish({"event": "approval", "approval_id": approval_id})
        await publish({"event": "done", "status": "awaiting_approval", "totals": {}})
        return {"run_id": run_id, "status": "awaiting_approval"}

    final = snap.values
    fstatus = final.get("status", "completed")
    totals = {
        "steps": final.get("budget", {}).get("steps_taken", 0),
        "cost_usd": final.get("budget", {}).get("cost_usd", 0.0),
        "llm_calls": final.get("budget", {}).get("llm_calls_made", 0),
    }
    await svc.finalize(
        session_id=s.id, status=fstatus, totals=totals, error=final.get("error")
    )
    await session.commit()
    await publish({"event": "done", "status": fstatus, "totals": totals})
    return {"run_id": run_id, "status": fstatus}


async def _run_or_resume(
    ctx: dict[str, Any], run_id: str, graph_input_factory: Any,
) -> dict[str, Any]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    channel = f"sse:ai:{run_id}"

    async def publish(event: dict[str, Any]) -> None:
        await redis.publish(channel, json.dumps(event, default=str))

    async with _session_for() as session:
        s = (
            await session.execute(select(AiSession).where(AiSession.run_id == run_id))
        ).scalar_one_or_none()
        if s is None:
            await record_failure(
                "run_agent", args=(run_id,), kwargs={},
                error=RuntimeError(f"run {run_id} not found"),
            )
            return {"run_id": run_id, "status": "missing"}
        try:
            graph_input = graph_input_factory(s)
            return await _drive(
                session=session, s=s, run_id=run_id, graph_input=graph_input,
                settings=settings, publish=publish,
            )
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise
            s2 = (
                await session.execute(select(AiSession).where(AiSession.run_id == run_id))
            ).scalar_one_or_none()
            if s2 is not None:
                await AgentService(session).finalize(
                    session_id=s2.id, status="error", totals={}, error=str(exc)[:500]
                )
                await session.commit()
            await publish({"event": "error", "message": "The run failed."})
            await publish({"event": "done", "status": "error", "totals": {}})
            await record_failure("run_agent", args=(run_id,), kwargs={}, error=exc)
            raise
        finally:
            await redis.aclose()


async def run_agent(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    def _fresh_init(s: AiSession) -> ManaState:
        cfg = s.run_config or {}
        return {
            "run_id": run_id,
            "session_id": str(s.id),
            "user_id": str(s.user_id),
            "goal": cfg.get("goal", "understand_job"),
            "inputs": cfg.get("inputs", {}),
            "budget": s.budget,  # type: ignore[typeddict-item]  # JSONB dict -> Budget
            "tool_cache": {},
            "step_log": [],
            "stop_requested": bool(cfg.get("stop")),
            "status": "running",
        }

    return await _run_or_resume(ctx, run_id, _fresh_init)


async def resume_agent(
    ctx: dict[str, Any], run_id: str, decision: str, note: str | None
) -> dict[str, Any]:
    def _resume_command(_s: AiSession) -> Command[str]:
        return Command(resume={"decision": decision, "note": note})

    return await _run_or_resume(ctx, run_id, _resume_command)
