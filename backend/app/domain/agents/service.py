"""``AgentService`` -- the domain service behind the ``/ai`` API and the
``run_agent`` worker task.

It owns the chat-session / message lifecycle, the run lifecycle
(``start_run`` -> enqueue, ``stop_run``, ``finalize``), and the two audit
trails the FE surfaces: the human-readable ``ai_actions`` log and the
machine ``agent_steps`` log. The LangGraph run itself lives in the worker;
this module only persists what the graph emits.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.queue import enqueue
from app.domain.agents.budget import budget_now, new_budget
from app.domain.agents.state import AgentGoal, StepEvent
from app.models.ai import AgentStep, AiAction, AiSession, Message


class AgentService:
    RUN_JOB = "run_agent"

    # A query is "job-shaped" when it reads like a search over roles. Phase 7a
    # does not route on it -- it is recorded in ``run_config["job_shaped"]`` so a
    # later NLU pass has the signal.
    _JOB_SHAPED = re.compile(
        r"\b(find|show|search|match|look|which|recommend)\b.*"
        r"\b(job|jobs|role|roles|position|opening)",
        re.I,
    )

    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------ #
    # sessions
    # ------------------------------------------------------------------ #
    async def create_session(
        self,
        user_id: uuid.UUID,
        *,
        kind: Literal["chat", "agent_run"] = "chat",
        context: dict[str, Any] | None = None,
    ) -> AiSession:
        session = AiSession(user_id=user_id, kind=kind, context=context or {})
        self._session.add(session)
        await self._session.flush()
        return session

    async def get_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> AiSession:
        session = (
            await self._session.execute(
                select(AiSession).where(
                    AiSession.id == session_id, AiSession.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if session is None:
            raise NotFoundError("Session not found")
        return session

    async def list_sessions(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[AiSession], int]:
        limit = max(1, min(limit, 50))
        offset = max(0, offset)
        total = (
            await self._session.execute(
                select(func.count())
                .select_from(AiSession)
                .where(AiSession.user_id == user_id)
            )
        ).scalar_one()
        rows = (
            await self._session.execute(
                select(AiSession)
                .where(AiSession.user_id == user_id)
                .order_by(AiSession.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    # ------------------------------------------------------------------ #
    # messages
    # ------------------------------------------------------------------ #
    async def recent_messages(
        self, session_id: uuid.UUID, *, limit: int = 30
    ) -> list[Message]:
        rows = (
            await self._session.execute(
                select(Message)
                .where(Message.ai_session_id == session_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        return list(reversed(rows))

    async def add_user_message(
        self, user_id: uuid.UUID, session_id: uuid.UUID, content: str
    ) -> Message:
        await self.get_session(user_id, session_id)
        message = Message(
            ai_session_id=session_id, user_id=user_id, role="user", content=content
        )
        self._session.add(message)
        await self._session.flush()
        return message

    # ------------------------------------------------------------------ #
    # run lifecycle
    # ------------------------------------------------------------------ #
    def infer_goal(self, content: str) -> tuple[AgentGoal, dict[str, Any]]:
        return "understand_job", {"query": content.strip()}

    async def start_run(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        *,
        goal: AgentGoal,
        inputs: dict[str, Any],
    ) -> str:
        session = await self.get_session(user_id, session_id)
        if session.status == "running":
            raise ValidationAppError("A run is already in progress for this session.")

        run_id = uuid.uuid4().hex
        session.run_id = run_id
        session.status = "running"
        session.goal = goal
        session.run_config = {
            "goal": goal,
            "inputs": inputs,
            "job_shaped": bool(self._JOB_SHAPED.search(inputs.get("query", ""))),
        }
        session.budget = dict(new_budget(now=budget_now()))
        session.started_at = datetime.now(UTC)
        session.ended_at = None
        session.error = None
        await self._session.flush()

        await enqueue(
            self.RUN_JOB, run_id, _defer_by=1.0, _job_id=f"run_agent:{run_id}"
        )
        return run_id

    async def stop_run(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        session = await self.get_session(user_id, session_id)
        if session.run_id:
            session.run_config = {**(session.run_config or {}), "stop": True}
            await self._session.flush()

    async def finalize(
        self,
        *,
        session_id: uuid.UUID,
        status: str,
        totals: dict[str, Any],
        error: str | None = None,
    ) -> None:
        session = await self._session.get(AiSession, session_id)
        if session is None:
            raise NotFoundError("Session not found")
        session.status = status
        session.totals = totals
        session.error = error
        session.ended_at = datetime.now(UTC)
        await self._session.flush()

    # ------------------------------------------------------------------ #
    # action log (human-readable) + step log (machine)
    # ------------------------------------------------------------------ #
    async def list_actions(
        self,
        user_id: uuid.UUID,
        *,
        session_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AiAction], int]:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        where = [AiAction.user_id == user_id]
        if session_id is not None:
            where.append(AiAction.ai_session_id == session_id)
        total = (
            await self._session.execute(
                select(func.count()).select_from(AiAction).where(*where)
            )
        ).scalar_one()
        rows = (
            await self._session.execute(
                select(AiAction)
                .where(*where)
                .order_by(AiAction.occurred_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def _log_action(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        run_id: str | None,
        node: str,
        action_key: str,
        summary: str,
        detail: dict[str, Any] | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        status: str = "ok",
        latency_ms: int | None = None,
        cost_usd: float | None = None,
    ) -> None:
        self._session.add(
            AiAction(
                user_id=user_id,
                ai_session_id=session_id,
                run_id=run_id,
                node=node,
                action_key=action_key,
                summary=summary,
                detail=detail or {},
                entity_type=entity_type,
                entity_id=entity_id,
                status=status,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
            )
        )
        await self._session.flush()

    async def _write_step(
        self, *, session_id: uuid.UUID, run_id: str, step: StepEvent
    ) -> None:
        self._session.add(
            AgentStep(
                ai_session_id=session_id,
                run_id=run_id,
                step_index=step["step_index"],
                node=step["node"],
                input_summary={},
                output_summary=step["detail"],
                llm_calls=step["llm_calls"],
                tool_calls={},
                tokens_in=0,
                tokens_out=0,
                cost_usd=step["cost_usd"],
                duration_ms=step["duration_ms"],
                status=step["status"],
            )
        )
        await self._session.flush()
