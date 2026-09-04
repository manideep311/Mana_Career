from sqlalchemy import select

from app.models.ai import AgentStep, AiAction, AiSession, Message


async def test_ai_session_message_action_step_roundtrip(db_session):
    from app.models.user import User

    u = User(email="ai-model@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()

    s = AiSession(user_id=u.id, kind="chat", status="running", run_id="r1",
                  run_config={"goal": "understand_job"})
    db_session.add(s)
    await db_session.flush()
    db_session.add_all([
        Message(ai_session_id=s.id, user_id=u.id, role="user", content="find jobs"),
        Message(ai_session_id=s.id, user_id=u.id, role="assistant", content="here",
                blocks=[{"kind": "text", "markdown": "here"}]),
        AiAction(user_id=u.id, ai_session_id=s.id, run_id="r1", node="job_retrieval",
                 action_key="searched", summary="Searched your job corpus"),
        AgentStep(ai_session_id=s.id, run_id="r1", step_index=0, node="job_retrieval",
                  status="ok"),
    ])
    await db_session.flush()
    msgs = (await db_session.execute(
        select(Message).where(Message.ai_session_id == s.id).order_by(Message.created_at)
    )).scalars().all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].blocks == [{"kind": "text", "markdown": "here"}]
    assert s.status == "running" and s.context == {}
