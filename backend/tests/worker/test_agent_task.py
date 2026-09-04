import contextlib
import decimal

from sqlalchemy import select

from app.domain.agents.service import AgentService
from app.models.ai import AgentStep, AiAction, AiSession, Message
from app.models.job import Job, JobChunk
from app.models.profile import CareerProfile, ProfileExperience
from app.models.skill import ProfileSkill, Skill
from app.models.user import User
from app.worker.tasks.agent import run_agent


@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


def _fake_redis_cls(fake_redis):
    return type("R", (), {"from_url": staticmethod(lambda *a, **k: fake_redis)})


async def _seed_profile(db_session, email):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    p = CareerProfile(
        user_id=u.id, seniority="senior", years_experience=decimal.Decimal("6")
    )
    s = Skill(slug="python", label="Python", category="language")
    db_session.add_all([p, s])
    await db_session.flush()
    db_session.add(
        ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id, source="user")
    )
    db_session.add(
        ProfileExperience(
            user_id=u.id, profile_id=p.id, company="A", title="ML Engineer",
            source="user", order_index=0, tech=["Python"],
        )
    )
    await db_session.flush()
    return u, p, s


async def _seed_job(db_session, skill, *, title):
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title=title, company="Acme",
        required_skills=[
            {"skill_id": str(skill.id), "slug": "python", "label": "Python", "weight": 0.9}
        ],
        preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    db_session.add(
        JobChunk(
            job_id=j.id, chunk_index=0, section="description", content="c",
            token_count=1, embed_model="fake-embed-1", embed_dim=1024,
            embedding=[0.1] * 1024,
        )
    )
    await db_session.flush()
    return j


async def _start(db_session, user):
    svc = AgentService(db_session)
    sess = await svc.create_session(user.id)
    run_id = await svc.start_run(
        user.id, sess.id, goal="understand_job", inputs={"query": "find ML roles"}
    )
    return sess, run_id


async def test_run_agent_completes_with_job_cards(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr(
        "app.worker.tasks.agent._session_for", lambda: _ctx(db_session)
    )
    monkeypatch.setattr(
        "app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis)
    )
    u, _p, skill = await _seed_profile(db_session, "agent-a@x.com")
    await _seed_job(db_session, skill, title="Senior ML Engineer")
    await _seed_job(db_session, skill, title="Staff ML Engineer")
    sess, run_id = await _start(db_session, u)

    out = await run_agent({}, run_id)
    assert out == {"run_id": run_id, "status": "completed"}

    row = (
        await db_session.execute(
            select(AiSession).where(AiSession.run_id == run_id)
        )
    ).scalar_one()
    assert row.status == "completed"

    msg = (
        await db_session.execute(
            select(Message).where(
                Message.ai_session_id == sess.id, Message.role == "assistant"
            )
        )
    ).scalar_one()
    kinds = [b["kind"] for b in msg.blocks]
    assert "text" in kinds
    assert kinds.count("job_card") >= 1

    steps = (
        await db_session.execute(
            select(AgentStep).where(AgentStep.run_id == run_id)
        )
    ).scalars().all()
    assert {"job_retrieval", "respond"} <= {st.node for st in steps}

    actions = (
        await db_session.execute(
            select(AiAction).where(AiAction.run_id == run_id)
        )
    ).scalars().all()
    assert actions


async def test_run_agent_insufficient_info_without_jobs(db_session, monkeypatch, fake_redis):
    monkeypatch.setattr(
        "app.worker.tasks.agent._session_for", lambda: _ctx(db_session)
    )
    monkeypatch.setattr(
        "app.worker.tasks.agent.Redis", _fake_redis_cls(fake_redis)
    )
    u, _p, _skill = await _seed_profile(db_session, "agent-b@x.com")
    sess, run_id = await _start(db_session, u)

    out = await run_agent({}, run_id)
    assert out == {"run_id": run_id, "status": "completed"}

    row = (
        await db_session.execute(
            select(AiSession).where(AiSession.run_id == run_id)
        )
    ).scalar_one()
    assert row.status == "completed"

    msg = (
        await db_session.execute(
            select(Message).where(
                Message.ai_session_id == sess.id, Message.role == "assistant"
            )
        )
    ).scalar_one()
    assert "insufficient_info" in [b["kind"] for b in msg.blocks]
