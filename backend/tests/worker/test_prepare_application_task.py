"""run_agent preparing a full application (résumé -> letter -> email) --
DB integration, CI-deferred."""
from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.agents.service import AgentService
from app.models.ai import AgentStep, AiAction, AiSession, Message
from app.models.application import ApplicationEmail, CoverLetter
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


async def test_run_agent_prepares_a_full_application(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr("app.worker.tasks.agent._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis))

    u, resume, job = await _seed(db_session, "prepare-app@x.com")
    svc = AgentService(db_session)
    sess = await svc.create_session(u.id, kind="agent_run")
    run_id = await svc.start_run(
        u.id, sess.id, goal="prepare_application",
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

    letter = (
        await db_session.execute(
            select(CoverLetter).where(CoverLetter.resume_version_id == version.id)
        )
    ).scalar_one()
    assert letter.job_id == job.id

    email = (
        await db_session.execute(
            select(ApplicationEmail).where(ApplicationEmail.job_id == job.id)
        )
    ).scalar_one()
    assert email.status == "draft"

    msg = (
        await db_session.execute(
            select(Message).where(Message.ai_session_id == sess.id, Message.role == "assistant")
        )
    ).scalar_one()
    assert "application_draft" in [b["kind"] for b in msg.blocks]

    steps = (
        await db_session.execute(select(AgentStep).where(AgentStep.run_id == run_id))
    ).scalars().all()
    assert {
        "resume_tailoring", "claim_validator", "cover_letter",
        "letter_claim_validator", "email_draft",
    } <= {st.node for st in steps}

    actions = (
        await db_session.execute(select(AiAction).where(AiAction.run_id == run_id))
    ).scalars().all()
    assert {a.action_key for a in actions} >= {
        "tailored_resume", "wrote_cover_letter", "drafted_email",
    }

    session_row = (
        await db_session.execute(select(AiSession).where(AiSession.run_id == run_id))
    ).scalar_one()
    assert session_row.status == "completed"
