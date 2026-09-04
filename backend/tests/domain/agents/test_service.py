import pytest

from app.core.errors import ValidationAppError
from app.domain.agents.service import AgentService
from app.models.user import User


async def _user(db_session, email="agent-svc@x.com"):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    return u


async def test_create_session_and_add_message(db_session):
    u = await _user(db_session)
    svc = AgentService(db_session)
    s = await svc.create_session(u.id, kind="chat")
    assert s.kind == "chat" and s.status == "idle"
    m = await svc.add_user_message(u.id, s.id, "find jobs that match my experience")
    assert m.role == "user" and m.content.startswith("find jobs")


def test_infer_goal_is_understand_job():
    # infer_goal is a pure classifier — no session needed, so this runs locally.
    svc = AgentService(None)  # type: ignore[arg-type]
    goal, inputs = svc.infer_goal("find jobs that match my experience")
    assert goal == "understand_job" and inputs == {"query": "find jobs that match my experience"}


async def test_start_run_sets_run_state_and_enqueues(db_session, monkeypatch):
    calls: list[str] = []

    async def _spy(task, *a, **k):
        calls.append(task)
        return "x"

    monkeypatch.setattr("app.domain.agents.service.enqueue", _spy)
    u = await _user(db_session, "agent-run@x.com")
    svc = AgentService(db_session)
    s = await svc.create_session(u.id)
    run_id = await svc.start_run(u.id, s.id, goal="understand_job", inputs={"query": "jobs"})
    await db_session.refresh(s)
    assert s.status == "running" and s.run_id == run_id and s.goal == "understand_job"
    assert s.run_config["goal"] == "understand_job" and "steps_taken" in s.budget
    assert calls == ["run_agent"]


async def test_start_run_rejects_a_concurrent_run(db_session):
    u = await _user(db_session, "agent-busy@x.com")
    svc = AgentService(db_session)
    s = await svc.create_session(u.id)
    await svc.start_run(u.id, s.id, goal="understand_job", inputs={})
    with pytest.raises(ValidationAppError):
        await svc.start_run(u.id, s.id, goal="understand_job", inputs={})
