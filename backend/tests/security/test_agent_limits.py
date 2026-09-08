"""The human-approval send gate is unbypassable; retry + step caps hold.

DB integration, CI-deferred, EXCEPT the static graph-edge check
(``test_email_action_has_only_the_human_approval_predecessor``), which is pure:
it compiles the graph with a stub ``deps`` and introspects the edge set, no
Postgres. The other four use the ``db_session`` fixture and ERROR at the
session-scoped ``_migrated`` fixture without a database (CI-only); they still
collect clean.

Prior coverage this module deliberately re-asserts from the security angle:

* ``tests/worker/test_resume_agent.py`` already drives pause -> approve -> send
  and pause -> reject -> no-send. Here the same flow is split into a matched
  positive/negative control so the invariant is explicit: the send path runs
  ONLY when the resume decision is ``approve``; ``reject`` is terminal with
  nothing sent.
* ``tests/domain/agents/test_budget.py::test_guard_routes_to_halted_on_budget_breach``
  already covers ``guard()``'s ``max_steps`` breach in isolation. ``test_step_budget_halts_the_run``
  asserts the dimension it cannot: a real ``prepare_application`` run seeded
  with a tiny ``budget.max_steps`` halts end-to-end instead of running the full
  chain to a send.
* ``_run_or_resume`` has two failure branches: transient
  (``if ctx["job_try"] < MAX_TRIES: raise`` -- ARQ retries) and terminal.
  ``test_flaky_node_finalizes_as_error_after_max_tries`` drives both: a
  ``job_try < MAX_TRIES`` call re-raises WITHOUT finalizing; a
  ``job_try == MAX_TRIES`` call finalizes the session ``error`` and re-raises
  once -- the call returns, no infinite loop.
"""

from __future__ import annotations

import contextlib
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.domain.agents.graph import build_graph
from app.domain.agents.service import AgentService
from app.models.ai import AgentStep, AiSession
from app.models.application import Application, ApplicationEmail, ApprovalRequest
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.worker.tasks.agent import resume_agent, run_agent
from app.worker.tasks.resume import MAX_TRIES

SEND_NODE = "email_external_action"
GATE_NODE = "human_approval"
ENTRY_NODE = "__start__"


# --------------------------------------------------------------------------- #
# helpers -- mirrored from tests/worker/test_resume_agent.py
# --------------------------------------------------------------------------- #
@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


def _fake_redis_cls(fake_redis):
    return type("R", (), {"from_url": staticmethod(lambda *a, **k: fake_redis)})


def _patch_seams(monkeypatch, db_session, fake_redis) -> None:
    monkeypatch.setattr("app.worker.tasks.agent._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis))


async def _seed(db_session, email):
    u = User(email=email, password_hash="x", full_name="A. Dev")
    db_session.add(u)
    await db_session.flush()
    r = Resume(
        user_id=u.id, file_ref="r.pdf", content_type="application/pdf", size_bytes=100,
        status="extracted", is_primary=True,
        extraction={
            "full_name": "A. Dev", "summary": "Backend engineer.",
            "skills": ["python"], "experiences": [],
        },
    )
    r.confirmed_at = datetime.now(UTC)
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add_all([r, j])
    await db_session.flush()
    return u, r, j


async def _start_prepare_application(db_session, email):
    """Seed the fixtures + a ``prepare_application`` run; return (user, job, session, run_id)."""
    u, resume, job = await _seed(db_session, email)
    svc = AgentService(db_session)
    sess = await svc.create_session(u.id, kind="agent_run")
    run_id = await svc.start_run(
        u.id, sess.id, goal="prepare_application",
        inputs={"job_id": str(job.id), "resume_id": str(resume.id)},
    )
    return u, job, sess, run_id


async def _run_to_pause(db_session, run_id, job):
    """Assert the run parks at the interrupt and return (application, approval)."""
    assert await run_agent({}, run_id) == {"run_id": run_id, "status": "awaiting_approval"}
    application = (
        await db_session.execute(select(Application).where(Application.job_id == job.id))
    ).scalar_one()
    approval = (
        await db_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.application_id == application.id)
        )
    ).scalar_one()
    assert approval.status == "pending"
    return application, approval


# --------------------------------------------------------------------------- #
# 1. PURE -- the only edge into the side-effecting node comes from the gate
# --------------------------------------------------------------------------- #
def test_email_action_has_only_the_human_approval_predecessor() -> None:
    """Compile the graph and prove the one side-effecting node
    (``email_external_action`` -- it calls ``email_sender.send``) is wired so
    every path into it passes through ``human_approval``, the ``interrupt()``
    gate. Two assertions:

    1. direct: the only edge whose target is the send node is sourced at
       ``human_approval`` (and is conditional);
    2. reachability: with ``human_approval``'s outgoing edges severed, the send
       node is unreachable from ``__start__`` -- so no goal / router branch can
       drive to a send without first pausing for a person.
    """
    compiled = build_graph(SimpleNamespace(checkpointer=None))  # type: ignore[arg-type]
    edges = list(compiled.get_graph().edges)

    into_send = {e.source for e in edges if e.target == SEND_NODE}
    assert into_send == {GATE_NODE}, into_send
    assert edges  # guard against an empty introspection making the checks vacuous
    assert any(e.target == SEND_NODE for e in edges)  # the send node IS wired in
    assert all(e.conditional for e in edges if e.target == SEND_NODE)

    adjacency: dict[str, set[str]] = {}
    for e in edges:
        if e.source == GATE_NODE:
            continue  # cut every way OUT of the gate
        adjacency.setdefault(e.source, set()).add(e.target)

    seen: set[str] = set()
    stack = [ENTRY_NODE]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, ()))

    assert SEND_NODE not in seen, sorted(seen)
    assert GATE_NODE in seen  # sanity: the gate is still on the graph, just severed


# --------------------------------------------------------------------------- #
# 2. reject is terminal -- nothing is sent  (negative control for test 3)
# --------------------------------------------------------------------------- #
async def test_reject_ends_without_sending(db_session, monkeypatch, fake_redis) -> None:
    """DB-gated. Run to the ``awaiting_approval`` pause, resume with
    ``decision="reject"``; the run reaches a terminal non-sent state -- the
    email is never ``sent``, the application never ``applied``, the session
    ends ``rejected``."""
    _patch_seams(monkeypatch, db_session, fake_redis)
    u, job, _sess, run_id = await _start_prepare_application(
        db_session, "agent-limits-reject@x.com"
    )
    application, approval = await _run_to_pause(db_session, run_id, job)

    approval.status = "rejected"
    approval.decided_by = u.id
    approval.decided_at = datetime.now(UTC)
    await db_session.flush()

    out = await resume_agent({}, run_id, "reject", "not a fit")
    assert out == {"run_id": run_id, "status": "rejected"}

    email = (
        await db_session.execute(
            select(ApplicationEmail).where(ApplicationEmail.job_id == job.id)
        )
    ).scalar_one()
    assert email.status != "sent"
    assert email.sent_at is None

    await db_session.refresh(application)
    assert application.status != "applied"
    assert application.applied_at is None

    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "rejected"
    assert session_row.ended_at is not None


# --------------------------------------------------------------------------- #
# 3. approve opens the gate -- the send path runs  (positive control)
# --------------------------------------------------------------------------- #
async def test_approve_runs_the_send_path(db_session, monkeypatch, fake_redis) -> None:
    """DB-gated. Fresh run to the pause, resume with ``decision="approve"``;
    ``email_external_action`` executes with the ``ConsoleEmailSender`` -- the
    email is ``sent`` (provider ``console``) and the application is ``applied``.
    Proves the gate OPENS on approve, so test 2's "reject -> not sent" is a
    real signal rather than a no-op."""
    _patch_seams(monkeypatch, db_session, fake_redis)
    u, job, _sess, run_id = await _start_prepare_application(
        db_session, "agent-limits-approve@x.com"
    )
    application, approval = await _run_to_pause(db_session, run_id, job)

    approval.status = "approved"
    approval.decided_by = u.id
    approval.decided_at = datetime.now(UTC)
    await db_session.flush()

    out = await resume_agent({}, run_id, "approve", None)
    assert out == {"run_id": run_id, "status": "completed"}

    email = (
        await db_session.execute(
            select(ApplicationEmail).where(ApplicationEmail.job_id == job.id)
        )
    ).scalar_one()
    assert email.status == "sent"
    assert email.provider == "console"
    assert email.sent_at is not None

    await db_session.refresh(application)
    assert application.status == "applied"
    assert application.applied_at is not None

    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "completed"
    assert session_row.ended_at is not None


# --------------------------------------------------------------------------- #
# 4. F3 retry cap -- a permanently flaky node finalizes as error, no loop
# --------------------------------------------------------------------------- #
async def test_flaky_node_finalizes_as_error_after_max_tries(
    db_session, monkeypatch, fake_redis
) -> None:
    """DB-gated. Monkeypatch the raw ``supervisor`` node to always raise. With
    ``ctx["job_try"] < MAX_TRIES`` the transient branch re-raises WITHOUT
    finalizing (ARQ would retry); with ``ctx["job_try"] == MAX_TRIES`` the
    retry budget is spent, so ``_run_or_resume`` finalizes the session
    ``status="error"``, records the dead-letter, and re-raises once -- the call
    returns rather than looping."""
    _patch_seams(monkeypatch, db_session, fake_redis)

    async def _always_raises(state, *, deps):
        raise RuntimeError("flaky supervisor")

    monkeypatch.setattr("app.domain.agents.graph.supervisor", _always_raises)

    _u, _job, _sess, run_id = await _start_prepare_application(
        db_session, "agent-limits-flaky@x.com"
    )
    # Release the seed past a SAVEPOINT so the error path's ``session.rollback()``
    # does not discard it (see ``_session_for``'s docstring for the seam).
    await db_session.commit()

    # transient try: re-raises, session left untouched ("running", not finalized)
    with pytest.raises(RuntimeError, match="flaky supervisor"):
        await run_agent({"job_try": 1}, run_id)
    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "running"
    assert session_row.ended_at is None

    # retries exhausted: finalized as error, call returns (re-raises once)
    with pytest.raises(RuntimeError, match="flaky supervisor"):
        await run_agent({"job_try": MAX_TRIES}, run_id)

    await db_session.refresh(session_row)
    assert session_row.status == "error"
    assert session_row.ended_at is not None


# --------------------------------------------------------------------------- #
# 5. step budget -- a tiny max_steps halts the run end-to-end
# --------------------------------------------------------------------------- #
async def test_step_budget_halts_the_run(db_session, monkeypatch, fake_redis) -> None:
    """DB-gated. ``tests/domain/agents/test_budget.py::
    test_guard_routes_to_halted_on_budget_breach`` covers ``guard()``'s
    ``max_steps`` breach in isolation; this asserts the dimension it cannot --
    a real ``prepare_application`` run seeded with ``budget.max_steps == 1``
    (deadline pushed far out, so ``steps`` is the dimension that trips) halts
    after the first guarded node instead of running the full ~11-node chain to
    a send. The session finalizes non-``completed`` and a persisted
    ``AgentStep`` carries ``status == "budget_exceeded"``."""
    _patch_seams(monkeypatch, db_session, fake_redis)
    _u, job, sess, run_id = await _start_prepare_application(
        db_session, "agent-limits-budget@x.com"
    )

    sess.budget = {**sess.budget, "max_steps": 1, "deadline_ts": time.time() + 3600.0}
    await db_session.flush()

    out = await run_agent({}, run_id)
    assert out == {"run_id": run_id, "status": "halted"}
    assert out["status"] != "completed"

    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "halted"
    assert session_row.ended_at is not None
    assert session_row.error == "steps"
    assert session_row.totals.get("steps", 0) <= 1  # stopped at the cap, not unbounded

    steps = (
        await db_session.execute(select(AgentStep).where(AgentStep.run_id == run_id))
    ).scalars().all()
    assert any(st.status == "budget_exceeded" for st in steps), [st.status for st in steps]

    # the gate never opened -- nothing was assembled far enough to send
    email = (
        await db_session.execute(
            select(ApplicationEmail).where(ApplicationEmail.job_id == job.id)
        )
    ).scalar_one_or_none()
    assert email is None or email.status != "sent"
