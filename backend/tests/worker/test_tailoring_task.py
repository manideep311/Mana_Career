"""run_agent tailoring the résumé end-to-end — DB integration, CI-deferred."""
from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.agents.service import AgentService
from app.models.ai import AgentStep, AiAction, AiSession, Message
from app.models.job import Job
from app.models.resume import Resume
from app.models.resume_version import ResumeVersion
from app.models.user import User
from app.worker.tasks.agent import run_agent


@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


def _fake_redis_cls(fake_redis):
    return type("R", (), {"from_url": staticmethod(lambda *a, **k: fake_redis)})


async def _seed(db_session, email):
    u = User(email=email, password_hash="x", full_name="U")
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


async def test_run_agent_tailors_the_resume(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr("app.worker.tasks.agent._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis))

    u, resume, job = await _seed(db_session, "tailor-task@x.com")
    svc = AgentService(db_session)
    sess = await svc.create_session(u.id, kind="agent_run")
    run_id = await svc.start_run(
        u.id, sess.id, goal="tailor_resume",
        inputs={"job_id": str(job.id), "resume_id": str(resume.id)},
    )

    out = await run_agent({}, run_id)
    assert out == {"run_id": run_id, "status": "completed"}

    version = (
        await db_session.execute(
            select(ResumeVersion).where(
                ResumeVersion.resume_id == resume.id, ResumeVersion.kind == "ai_tailored"
            )
        )
    ).scalar_one()
    assert "claim_validation" in version.generation_meta

    msg = (
        await db_session.execute(
            select(Message).where(Message.ai_session_id == sess.id, Message.role == "assistant")
        )
    ).scalar_one()
    assert "resume_suggestion" in [b["kind"] for b in msg.blocks]

    steps = (
        await db_session.execute(select(AgentStep).where(AgentStep.run_id == run_id))
    ).scalars().all()
    assert {"resume_tailoring", "claim_validator"} <= {st.node for st in steps}

    actions = (
        await db_session.execute(select(AiAction).where(AiAction.run_id == run_id))
    ).scalars().all()
    assert actions

    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "completed"
