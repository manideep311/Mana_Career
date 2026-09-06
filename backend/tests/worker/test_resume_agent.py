"""run_agent pausing at human_approval, resume_agent resuming it -- DB
integration, CI-deferred. The critical test of Phase 10a."""
from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.agents.service import AgentService
from app.models.ai import AiSession
from app.models.application import Application, ApplicationEmail, ApprovalRequest
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.worker.tasks.agent import resume_agent, run_agent


@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


def _fake_redis_cls(fake_redis):
    return type("R", (), {"from_url": staticmethod(lambda *a, **k: fake_redis)})


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


async def test_run_agent_pauses_then_resume_agent_sends(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr("app.worker.tasks.agent._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis))

    u, resume, job = await _seed(db_session, "resume-agent@x.com")
    svc = AgentService(db_session)
    sess = await svc.create_session(u.id, kind="agent_run")
    run_id = await svc.start_run(
        u.id, sess.id, goal="prepare_application",
        inputs={"job_id": str(job.id), "resume_id": str(resume.id)},
    )

    # --- first invocation: runs to the interrupt and STOPS, nothing sent ---
    out = await run_agent({}, run_id)
    assert out == {"run_id": run_id, "status": "awaiting_approval"}

    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "awaiting_approval"
    assert session_row.ended_at is None  # not finalized -- still paused, not done

    application = (
        await db_session.execute(select(Application).where(Application.job_id == job.id))
    ).scalar_one()
    assert application.status == "awaiting_approval"

    email = (
        await db_session.execute(
            select(ApplicationEmail).where(ApplicationEmail.job_id == job.id)
        )
    ).scalar_one()
    assert email.status == "draft"  # not sent yet

    approval = (
        await db_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.application_id == application.id)
        )
    ).scalar_one()
    assert approval.status == "pending"

    # --- decide + resume: mirrors what POST /approvals/{id} does ---
    approval.status = "approved"
    approval.decided_by = u.id
    approval.decided_at = datetime.now(UTC)
    await db_session.flush()

    out2 = await resume_agent({}, run_id, "approve", None)
    assert out2 == {"run_id": run_id, "status": "completed"}

    await db_session.refresh(session_row)
    assert session_row.status == "completed"
    assert session_row.ended_at is not None

    await db_session.refresh(application)
    assert application.status == "applied"
    assert application.applied_at is not None

    await db_session.refresh(email)
    assert email.status == "sent"
    assert email.provider == "console"
    assert email.provider_message_id and email.provider_message_id.startswith("console-")
    assert email.sent_at is not None


async def test_run_agent_pauses_then_resume_agent_rejects(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr("app.worker.tasks.agent._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis))

    u, resume, job = await _seed(db_session, "resume-agent-reject@x.com")
    svc = AgentService(db_session)
    sess = await svc.create_session(u.id, kind="agent_run")
    run_id = await svc.start_run(
        u.id, sess.id, goal="prepare_application",
        inputs={"job_id": str(job.id), "resume_id": str(resume.id)},
    )
    await run_agent({}, run_id)

    application = (
        await db_session.execute(select(Application).where(Application.job_id == job.id))
    ).scalar_one()
    approval = (
        await db_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.application_id == application.id)
        )
    ).scalar_one()
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
    assert email.status == "draft"  # never sent -- reject is terminal (R8)
